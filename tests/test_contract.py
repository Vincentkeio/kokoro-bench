"""Test installation and NDJSON using fake tools; no network or VPS load."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "kokoro-bench.sh"
BASH = shutil.which("bash") or r"C:\Program Files\Git\bin\bash.exe"

def shell_path(path):
    value = str(pathlib.Path(path)).replace("\\", "/")
    return "/" + value[0].lower() + value[2:] if len(value) > 1 and value[1] == ":" else value

class ContractTests(unittest.TestCase):
    def run_script(self, only, install=True, prepare=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            binary = root / "bin"
            binary.mkdir()
            def tool(name, content):
                file = binary / name
                file.write_text("#!/usr/bin/env bash\n" + content, encoding="utf-8", newline="\n")
                file.chmod(0o755)
            (root / "sysbench-source").write_text('''#!/usr/bin/env bash
case "$*" in
  *--memory-oper=read*) echo '16384.00 MiB transferred (5123.50 MiB/sec)' ;;
  *--memory-oper=write*) echo '16384.00 MiB transferred (4567.25 MiB/sec)' ;;
  *--threads=1*) echo 'events per second: 321.00' ;;
  *) echo 'events per second: 654.00' ;;
esac
''', encoding="utf-8", newline="\n")
            tool("id", "echo 0\n")
            tool("sleep", "exit 0\n")
            tool("apt-get", '''case "$*" in
*update*) touch "$FIXTURE_ROOT/refreshed" ;;
*install*) [ -f "$FIXTURE_ROOT/refreshed" ] || exit 1
cp "$FIXTURE_ROOT/sysbench-source" "$FIXTURE_ROOT/bin/sysbench"
chmod 755 "$FIXTURE_ROOT/bin/sysbench" ;;
*) exit 1 ;;
esac
'''.replace('chmod 755 "$FIXTURE_ROOT/bin/sysbench" ;;','chmod 755 "$FIXTURE_ROOT/bin/sysbench"\nfor tool in fio speedtest-cli; do cp "$FIXTURE_ROOT/bin/sysbench" "$FIXTURE_ROOT/bin/$tool"; done ;;'))
            tool("python3", 'exec "$FIXTURE_PYTHON" "$@"\n')
            (root / "upstream").write_text('''#!/usr/bin/env bash
private=no
while [ $# -gt 0 ]; do
  case "$1" in -p) private=yes; shift ;; -o) output="$2"; shift 2 ;; *) shift ;; esac
done
[ "$private" = yes ] && [ -n "$output" ] || exit 23
printf '%s' '{"Info":{"Type":"机房","ASN":"AS123","Organization":"192.0.2.10"},"Type":{"Usage":{"IPinfo":"机房"}},"Media":{"Netflix":{"Status":"解锁"}},"Score":{"AbuseIPDB":"0"}}' > "$output"
echo 'progress only, no JSON on stdout'
printf '\n%s\n' '{"Info":{"Type":"住宅"},"Type":{"Usage":{"IPinfo":"住宅"}}}' >> "$output"
''', encoding="utf-8", newline="\n")
            tool("curl", 'cat "$FIXTURE_ROOT/upstream"\n')
            tool("nexttrace", "printf '%s\\n' '{\"Hops\":[[{\"Geo\":{\"asnumber\":\"4134\"}}]]}'\n")
            env = os.environ.copy()
            env["FIXTURE_ROOT"] = shell_path(root)
            env["PYTHONUTF8"] = "1"
            env["FIXTURE_PYTHON"] = shell_path(sys.executable)
            env["PATH"] = str(binary) + (":" if os.name != "nt" else ";") + env["PATH"]
            env["FIXTURE_SCRIPT"] = shell_path(SCRIPT)
            env["FIXTURE_ONLY"] = only
            env["FIXTURE_NO_INSTALL"] = ("" if install else "--no-install") + (" --prepare-only" if prepare else "")
            command = [BASH, "-c", 'export PATH="$FIXTURE_ROOT/bin:/usr/bin:/bin"; exec bash "$FIXTURE_SCRIPT" --only "$FIXTURE_ONLY" ${FIXTURE_NO_INSTALL:-}']
            result = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.last_stderr = result.stderr
            self.assertEqual(result.returncode, 0, result.stderr)
            return [json.loads(line) for line in result.stdout.splitlines()], result.stdout

    def test_missing_sysbench_installs_and_reports_cpu_and_memory(self):
        events, _ = self.run_script("cpu,memory")
        results = {event["test"]: event for event in events if event["event"] == "result"}
        self.assertTrue(results["cpu"]["ok"], str(results["cpu"])+self.last_stderr)
        self.assertEqual(results["cpu"]["data"]["single_eps"], 321)
        self.assertEqual(results["memory"]["data"]["read_mib_s"], 5123.5)
        self.assertEqual(results["memory"]["data"]["write_mib_s"], 4567.25)
        self.assertTrue(events[-1]["ok"])

    def test_install_disabled_reports_failure_in_done(self):
        events, _ = self.run_script("memory", install=False)
        self.assertFalse(events[-1]["ok"])
        self.assertIn("memory", events[-1]["failed"])

    def test_ipquality_reads_private_json_file_and_hides_ip(self):
        events, raw = self.run_script("ip")
        result = next(event for event in events if event["event"] == "result")
        self.assertTrue(result["ok"], str(result)+self.last_stderr)
        self.assertEqual(result["data"]["usage"], "机房")
        self.assertNotIn("192.0.2.10", raw)

    def test_route_reports_all_three_carriers(self):
        events, _ = self.run_script("route")
        route = next(event for event in events if event["event"] == "result")
        self.assertTrue(route["ok"], self.last_stderr)
        for carrier in ["电信", "联通", "移动"]:
            self.assertIn("163", route["data"][carrier]["line"])
            self.assertIn("深圳", route["data"][carrier]["line"])

    def test_prepare_only_installs_components_without_running_benchmarks(self):
        events, _ = self.run_script("", prepare=True)
        self.assertEqual(events, [])

if __name__ == "__main__": unittest.main()
