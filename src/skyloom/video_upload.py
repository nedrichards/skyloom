"""Bounded MP4 preparation and the Bluesky video preprocessing upload protocol.

Upload contract: https://bsky.network/docs/about-bluesky-content/video/
Current size/duration caps: bluesky-social/social-app src/lib/constants.ts.
"""

import asyncio
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx
from atproto import models
from pydantic import ValidationError

from .errors import UserError
from .richtext import counts

MAX_VIDEO_BYTES = 300_000_000
MAX_VIDEO_SECONDS = 600
VIDEO_SERVICE = "https://video.bsky.app"
VIDEO_DID = "did:web:video.bsky.app"


@dataclass(frozen=True, slots=True)
class VideoAttachment:
    path: str
    alt: str = ""
    duration: float = 0
    width: int = 0
    height: int = 0


def validate_video(attachment):
    if not attachment.alt.strip():
        return "Add a description for the video."
    characters, size = counts(attachment.alt)
    if characters > 1000 or size > 10_000:
        return "Video descriptions allow 1000 characters and 10000 UTF-8 bytes."
    return ""


def _run(command, *, timeout=120, cancel=None):
    """Never retain ffmpeg diagnostics containing private file names or metadata."""
    if cancel is not None and cancel.is_set():
        raise UserError("Video preparation was cancelled.")
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(  # noqa: S603 — fixed executables/flags; input paths are separate argv entries.
                command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL
            )
        except OSError:
            raise UserError(
                "Video preparation is unavailable. Reinstall Skyloom and try again."
            ) from None
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel is not None and cancel.is_set():
                    raise UserError("Video preparation was cancelled.")
                if time.monotonic() - started >= timeout:
                    raise UserError("Video preparation took too long. Try a smaller clip.")
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise UserError(
                    "This video could not be read. Choose an MP4 with H.264 video and AAC audio."
                )
            if cancel is not None and cancel.is_set():
                raise UserError("Video preparation was cancelled.")
            if output.tell() > 1_000_000:
                raise UserError("This video has too much metadata. Choose another clip.")
            output.seek(0)
            return output.read(1_000_001)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def inspect_video(path, *, cancel=None):
    path = Path(path).resolve()
    try:
        size = path.stat().st_size
    except OSError:
        raise UserError("The video is no longer available. Choose it again.") from None
    if not 0 < size <= MAX_VIDEO_BYTES:
        raise UserError("Choose a video smaller than 300 MB.")
    payload = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,width,height:stream_side_data=rotation",
            "-of",
            "json",
            str(path),
        ],
        timeout=30,
        cancel=cancel,
    )
    try:
        info = json.loads(payload)
        streams = info["streams"]
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = float(info["format"]["duration"])
        width, height = int(video["width"]), int(video["height"])
        formats = info["format"]["format_name"].split(",")
    except ValueError, KeyError, TypeError, StopIteration:
        raise UserError(
            "This video has invalid duration or dimensions. Choose another MP4."
        ) from None
    if (
        "mp4" not in formats
        or video.get("codec_name") != "h264"
        or any(
            stream.get("codec_type") == "audio" and stream.get("codec_name") != "aac"
            for stream in streams
        )
    ):
        raise UserError("Choose an MP4 with H.264 video and AAC audio.")
    if not math.isfinite(duration) or not 0 < duration <= MAX_VIDEO_SECONDS:
        raise UserError("Choose a video no longer than 10 minutes.")
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        raise UserError("Choose a video with dimensions no larger than 8192 pixels.")
    for side in video.get("side_data_list", []):
        if int(side.get("rotation", 0)) % 180:
            width, height = height, width
    return VideoAttachment(str(path), duration=duration, width=width, height=height)


def prepare_video(path, directory, *, cancel=None):
    """Called under Storage's account IO lease; the original file is untouched."""
    source = inspect_video(path, cancel=cancel)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".video-", suffix=".mp4", dir=directory)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        _run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                source.path,
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-map_metadata",
                "-1",
                "-map_metadata:s",
                "-1",
                "-map_chapters",
                "-1",
                "-fflags",
                "+bitexact",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            cancel=cancel,
        )
        prepared = inspect_video(temporary, cancel=cancel)
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        target = directory / (digest + ".mp4")
        if cancel is not None and cancel.is_set():
            raise UserError("Video preparation was cancelled.")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        return VideoAttachment(
            str(target), duration=prepared.duration, width=prepared.width, height=prepared.height
        )
    finally:
        temporary.unlink(missing_ok=True)


def pds_audience(service):
    endpoint = (
        getattr(getattr(service.client, "_session", None), "pds_endpoint", None)
        or service.client._base_url
    )
    url = urlparse(str(endpoint))
    if (
        url.scheme != "https"
        or not url.hostname
        or "@" in url.netloc
        or url.password
        or url.query
        or url.fragment
    ):
        raise UserError("Video uploads require a valid HTTPS account server.")
    # did:web encodes a nonstandard port in its hostname component.
    return "did:web:" + quote(url.netloc, safe=".")


@asynccontextmanager
async def _client(client):
    if client is not None:
        yield client
    else:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(30, write=120),
            limits=httpx.Limits(max_connections=2),
        ) as created:
            yield created


async def _json(client, method, name, *, allowed=(200,), **kwargs):
    async with client.stream(
        method, VIDEO_SERVICE + "/xrpc/app.bsky.video." + name, follow_redirects=False, **kwargs
    ) as response:
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > 1_000_000:
                raise UserError("The video service returned an invalid response.")
        if response.status_code not in allowed:
            if response.status_code in (401, 403):
                raise UserError(
                    "Video uploads are not permitted for this account. Check email verification and account eligibility in Bluesky."
                )
            if response.status_code == 429:
                raise UserError(
                    "The video upload limit has been reached. Wait before trying again."
                )
            raise UserError(
                "The video service could not complete this action. Your draft is kept; check your profile before trying again."
            )
        try:
            result = json.loads(content)
        except ValueError, UnicodeError:
            raise UserError("The video service returned an invalid response.") from None
        if not isinstance(result, dict):
            raise UserError("The video service returned an invalid response.")
        return result


async def upload_video(service, attachment, *, http_client=None, poll_interval=1, poll_limit=180):
    try:
        async with asyncio.timeout(600):
            return await _upload_video(
                service,
                attachment,
                http_client=http_client,
                poll_interval=poll_interval,
                poll_limit=poll_limit,
            )
    except TimeoutError:
        raise UserError(
            "Video uploading took too long. Your draft is kept; check your profile before trying again."
        ) from None


async def _upload_video(service, attachment, *, http_client, poll_interval, poll_limit):
    """Called inside Service.authenticated(); uploads once and never publishes a post."""
    if error := validate_video(attachment):
        raise UserError(error)
    inspected = await asyncio.to_thread(inspect_video, attachment.path)
    did = service.account.did
    file_size = await asyncio.to_thread(lambda: Path(inspected.path).stat().st_size)
    if not 0 < file_size <= MAX_VIDEO_BYTES:
        raise UserError("The video changed after preparation. Choose it again.")

    async def token(audience, lexicon, lifetime):
        result = await service.client.com.atproto.server.get_service_auth(
            {"aud": audience, "lxm": lexicon, "exp": int(time.time()) + lifetime}
        )
        return result.token

    async with _client(http_client) as client:
        limits_token = await token(VIDEO_DID, "app.bsky.video.getUploadLimits", 60)
        limits = await _json(
            client, "GET", "getUploadLimits", headers={"Authorization": "Bearer " + limits_token}
        )
        if limits.get("canUpload") is not True:
            raise UserError(
                "Video uploads are not permitted for this account. Check email verification and account eligibility in Bluesky."
            )
        remaining = limits.get("remainingDailyBytes")
        videos = limits.get("remainingDailyVideos")
        if (isinstance(remaining, int) and remaining < file_size) or (
            isinstance(videos, int) and videos <= 0
        ):
            raise UserError(
                "Your remaining daily video allowance is too small for this clip. Wait before trying again."
            )
        upload_token = await token(pds_audience(service), "com.atproto.repo.uploadBlob", 1800)

        async def chunks():
            stream = await asyncio.to_thread(Path(inspected.path).open, "rb")
            sent = 0
            try:
                while chunk := await asyncio.to_thread(stream.read, 256 * 1024):
                    sent += len(chunk)
                    if sent > file_size or sent > MAX_VIDEO_BYTES:
                        raise UserError("The video changed after preparation. Choose it again.")
                    yield chunk
                if sent != file_size:
                    raise UserError("The video changed after preparation. Choose it again.")
            finally:
                await asyncio.to_thread(stream.close)

        job = await _json(
            client,
            "POST",
            "uploadVideo",
            allowed=(200, 202, 409),
            params={"did": did, "name": uuid4().hex + ".mp4"},
            headers={
                "Authorization": "Bearer " + upload_token,
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
            },
            content=chunks(),
        )
        job = job.get("jobStatus", job)
        expected_job = None
        for attempt in range(poll_limit + 1):
            if (
                not isinstance(job, dict)
                or job.get("did") != did
                or not isinstance(job.get("jobId"), str)
                or not 0 < len(job["jobId"]) <= 256
            ):
                raise UserError("The video service returned an invalid processing job.")
            if expected_job is not None and job["jobId"] != expected_job:
                raise UserError("The video service returned a different processing job.")
            expected_job = job["jobId"]
            if blob := job.get("blob"):
                if (
                    not isinstance(blob, dict)
                    or blob.get("mimeType") != "video/mp4"
                    or type(blob.get("size")) is not int
                    or not 0 < blob["size"] <= MAX_VIDEO_BYTES
                ):
                    raise UserError("The video service returned an invalid video blob.")
                try:
                    return models.AppBskyEmbedVideo.Main(
                        video=blob,
                        alt=attachment.alt,
                        aspect_ratio={"width": inspected.width, "height": inspected.height},
                    )
                except ValidationError, ValueError, TypeError:
                    raise UserError("The video service returned an invalid video blob.") from None
            if job.get("error") != "already_exists" and (
                job.get("state") == "JOB_STATE_FAILED" or job.get("error")
            ):
                raise UserError(
                    "Bluesky could not process this video. Your draft is kept; choose another clip or try again later."
                )
            if attempt == poll_limit:
                break
            await asyncio.sleep(poll_interval)
            result = await _json(client, "GET", "getJobStatus", params={"jobId": expected_job})
            job = result.get("jobStatus", result)
    raise UserError(
        "Video processing took too long. Your draft is kept; check your profile before trying again."
    )
