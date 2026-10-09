"""Smoke-test a frozen engine: python packaging/smoke_engine.py <path-to-sapient-api>"""
import json
import secrets
import subprocess
import sys
import tempfile
import urllib.request


def get(url, token=None):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None


def main(exe):
    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as data:
        proc = subprocess.Popen([exe, "--data-dir", data], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True)
        try:
            proc.stdin.write(token + "\n")
            proc.stdin.flush()
            event = json.loads(proc.stdout.readline())
            assert event["event"] == "ready", event
            base = f"http://127.0.0.1:{event['port']}/api"
            assert get(base + "/health")[0] == 200
            assert get(base + "/profile")[0] == 401
            status, profile = get(base + "/profile", token)
            assert status == 200 and profile["display_name"] == "Investor", (status, profile)
            status, settings = get(base + "/ai/settings", token)
            assert status == 200 and settings["mode"] == "off", (status, settings)
            status, results = get(base + "/stocks/search?q=BHP&market=ASX", token)
            assert status == 200 and results, (status, results)
            proc.stdin.close()
            assert proc.wait(timeout=30) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
    print("engine smoke test passed")


if __name__ == "__main__":
    main(sys.argv[1])
