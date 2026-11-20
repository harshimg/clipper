"""Self-host Projects tab: list, cancel and delete jobs (/api/local/projects,
/api/jobs/{id}/cancel, DELETE /api/jobs/{id}). Off when billing is on."""
import asyncio
import json
import os

import httpx
import pytest

app_module = pytest.importorskip("app")

J1 = "11111111-1111-4111-8111-111111111111"
J2 = "22222222-2222-4222-8222-222222222222"


def _call(method, path):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(method, path)
    return asyncio.run(_do())


@pytest.fixture()
def disk(tmp_path, monkeypatch):
    out_root = tmp_path / "output"; up_root = tmp_path / "uploads"
    out_root.mkdir(); up_root.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out_root))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(up_root))
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "job_queue", asyncio.PriorityQueue())
    monkeypatch.setattr(app_module, "_cancelled_jobs", set())
    monkeypatch.setattr(app_module, "_job_processes", {})
    return out_root, up_root


def _finished_job(out_root, job_id=J1):
    d = out_root / job_id
    d.mkdir()
    (d / "My_Video_metadata.json").write_text(json.dumps({"shorts": []}))
    (d / "My_Video_clip_1.mp4").write_bytes(b"x" * 1000)
    (d / "My_Video_clip_2.mp4").write_bytes(b"x" * 1000)
    return d


def _queued_job(out_root, up_root, job_id=J2):
    d = out_root / job_id
    d.mkdir()
    upload = up_root / "source.mp4"
    upload.write_bytes(b"y" * 5000)
    cmd = ["python", "-u", "main.py", "-i", str(upload), "-o", str(d)]
    (d / ".resume.json").write_text(json.dumps({"cmd": cmd}))
    app_module.jobs[job_id] = {"status": "queued", "cmd": cmd,
                               "logs": app_module._TimedLog([f"Job {job_id} queued."]),
                               "submitted_at": 2.0}
    return d, upload


def test_lists_every_job_on_disk(disk):
    out_root, up_root = disk
    _finished_job(out_root)
    _queued_job(out_root, up_root)
    (out_root / "thumbnails").mkdir()  # not a job dir
    r = _call("GET", "/api/local/projects")
    assert r.status_code == 200
    by_id = {p["job_id"]: p for p in r.json()["projects"]}
    assert set(by_id) == {J1, J2}
    assert by_id[J1]["status"] == "completed" and by_id[J1]["clips"] == 2
    assert by_id[J1]["title"] == "My Video" and by_id[J1]["size_bytes"] > 2000
    assert by_id[J2]["status"] == "queued" and by_id[J2]["source"] == "source.mp4"


def test_cancel_a_queued_job_for_good(disk):
    out_root, up_root = disk
    d, _ = _queued_job(out_root, up_root)
    r = _call("POST", f"/api/jobs/{J2}/cancel")
    assert r.status_code == 200 and r.json()["was_active"] is True
    job = app_module.jobs[J2]
    assert job["status"] == "failed" and job["cancelled"]
    assert job["logs"][-1] == app_module.CANCELLED_LOG
    assert J2 in app_module._cancelled_jobs
    # A restart neither resumes it nor calls it a queue timeout.
    assert not (d / ".resume.json").exists()
    assert (d / ".queue_expired").read_text() == "cancelled"
    assert not app_module._should_auto_retry(job)
    listed = {p["job_id"]: p for p in _call("GET", "/api/local/projects").json()["projects"]}
    assert listed[J2]["status"] == "cancelled"


def test_cancel_kills_the_running_process(disk, monkeypatch):
    out_root, up_root = disk
    _queued_job(out_root, up_root)
    app_module.jobs[J2]["status"] = "processing"

    class _Proc:
        pid = 4242
        def poll(self):
            return None
    killed = []
    monkeypatch.setattr(app_module, "_kill_job_process", lambda p: killed.append(p.pid))
    app_module._job_processes[J2] = _Proc()
    assert _call("POST", f"/api/jobs/{J2}/cancel").status_code == 200
    assert killed == [4242]


def test_delete_removes_the_folder_and_the_upload(disk):
    out_root, up_root = disk
    d, upload = _queued_job(out_root, up_root)
    r = _call("DELETE", f"/api/jobs/{J2}")
    assert r.status_code == 200 and r.json()["freed_bytes"] >= 5000
    assert not d.exists() and not upload.exists()
    assert J2 not in app_module.jobs and J2 in app_module._cancelled_jobs


def test_delete_keeps_an_upload_another_job_uses(disk):
    out_root, up_root = disk
    d, upload = _queued_job(out_root, up_root)
    app_module.jobs[J1] = {"status": "queued", "cmd": app_module.jobs[J2]["cmd"],
                           "logs": app_module._TimedLog([])}
    assert _call("DELETE", f"/api/jobs/{J2}").status_code == 200
    assert not d.exists() and upload.exists()


def test_bad_ids_and_unknown_jobs(disk):
    assert _call("DELETE", "/api/jobs/not-a-job").status_code == 400
    assert _call("POST", f"/api/jobs/{J1}/cancel").status_code == 404
    assert _call("DELETE", f"/api/jobs/{J1}").status_code == 404


def test_off_with_billing(disk, monkeypatch):
    out_root, _ = disk
    _finished_job(out_root)
    monkeypatch.setattr(app_module, "BILLING_ENABLED", True)
    assert _call("GET", "/api/local/projects").status_code == 404
    assert _call("DELETE", f"/api/jobs/{J1}").status_code == 404
    assert (out_root / J1).exists()
