import asyncio
import json
import uuid
import psutil
import os
from redis import StrictRedis, ConnectionPool
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from typing import Any, List, Union, Dict
from pydantic import UUID4, BaseModel
from apscheduler.schedulers.background import BackgroundScheduler


REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = os.getenv('REDIS_PORT', '6379')
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', None)
COOKIE_FILE = os.getenv('COOKIE_FILE', '/data/cookies.txt')

JOB_SIG_READY = 'ready'
JOB_SIG_DOWNLOADING = 'downloading'
JOB_SIG_FINISH = 'finish'


app = FastAPI()


rpool = ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)


class RedisConn:
    def __init__(self) -> None:
        self._conn = None
        self._connect()
        self.PREFIX = 'piapi.youget'

    def _connect(self) -> None:
        self._conn = StrictRedis(connection_pool=rpool, 
                                 decode_responses='UTF-8', encoding='UTF-8')

    def set_job_with_ready(self, job_uuid: str, video_name: str, url: str, metadata: str):
        rc = self._conn
        pipe = rc.pipeline()
        pipe.lpush(f"{self.PREFIX}.jobs", job_uuid)
        pipe.set(f"{self.PREFIX}.job.{job_uuid}.status", JOB_SIG_READY)
        pipe.set(f"{self.PREFIX}.job.{job_uuid}.video_name", video_name)
        pipe.set(f"{self.PREFIX}.job.{job_uuid}.url", url)
        pipe.set(f"{self.PREFIX}.job.{job_uuid}.pid", '')
        pipe.set(f"{self.PREFIX}.job.{job_uuid}.metadata", metadata)
        pipe.execute()

    def set_job_with_downloading(self, uuid) -> None:
        rc = self._conn
        rc.set(f"{self.PREFIX}.job.{uuid}.status", JOB_SIG_DOWNLOADING)

    def set_job_with_finish(self, uuid) -> None:
        rc = self._conn
        rc.set(f"{self.PREFIX}.job.{uuid}.status", JOB_SIG_FINISH)

    def set_job_pid(self, uuid, pid) -> None:
        rc = self._conn
        rc.set(f"{self.PREFIX}.job.{uuid}.pid", pid)

    def get_job_with_uuid(self, uuid) -> dict:
        rc = self._conn
        video_name, url, status, pid, metadata = rc.mget(
                f"{self.PREFIX}.job.{uuid}.video_name",
                f"{self.PREFIX}.job.{uuid}.url",
                f"{self.PREFIX}.job.{uuid}.status",
                f"{self.PREFIX}.job.{uuid}.pid",
                f"{self.PREFIX}.job.{uuid}.metadata"
        )
        return dict(video_name=video_name.decode(),
                    url=url.decode(),
                    status=status.decode(),
                    pid=pid.decode(),
                    metadata=metadata.decode())

    def get_job_with_uuid_nometadata(self, uuid) -> dict:
        rc = self._conn
        video_name, url, status, pid = rc.mget(
                f"{self.PREFIX}.job.{uuid}.video_name",
                f"{self.PREFIX}.job.{uuid}.url",
                f"{self.PREFIX}.job.{uuid}.status",
                f"{self.PREFIX}.job.{uuid}.pid",
        )
        return dict(video_name=video_name.decode(),
                    url=url.decode(),
                    status=status.decode(),
                    pid=pid.decode())

    def get_jobs_uuids(self) -> list:
        rc = self._conn
        jobs = [ _.decode() for _ in 
                rc.lrange(f"{self.PREFIX}.jobs", 0, -1)]
        return jobs
        
    def get_jobs_to_inte_dict(self, retuuid: bool = False, nometadata: bool = False) -> Any:
        jobs = self.get_jobs_uuids()

        for job_uuid in jobs:
            ret_job = self.get_job_with_uuid_nometadata(job_uuid) if nometadata else self.get_job_with_uuid(job_uuid)
            if retuuid:
                yield job_uuid, ret_job
            else:
                yield ret_job

    def get_job_uuid_with_url(self, url) -> str:
        jobs_uuids = self.get_jobs_uuids()
        for job_uuid in jobs_uuids:
            job = self.get_job_with_uuid_nometadata(job_uuid)
            if url == job.get('url'):
                return job_uuid
            else:
                return ''

    def get_job_metadata_raw(self, uuid) -> str:
        rc = self._conn
        return rc.get(f"{self.PREFIX}.job.{uuid}.metadata").decode()

    def get_job_metadata_dict(self, uuid) -> dict:
        return json.loads(self.get_job_metadata_raw(uuid))

    def update_jobs_status(self) -> None:
        for uuid, job in self.get_jobs_to_inte_dict(retuuid=True, nometadata=True):
            pid = job['pid']
            if pid:
                is_running = True if pid in (str(p.pid) for p in psutil.process_iter()) else False
                if not is_running:
                    self.set_job_with_finish(uuid)

    def update_job_status(self, uuid) -> None:
        job = self.get_job_with_uuid(uuid)
        pid = job['pid']
        if pid:
            is_running = True if pid in (str(p.pid) for p in psutil.process_iter()) else False
            if not is_running:
                self.set_job_with_finish(uuid)


def job():
    rc = RedisConn()._conn
    jobs = rc.lrange('piapi.youget.jobs', 0, -1)
    if jobs:
        for job in jobs:
            job = job.decode()
            if not rc.get(f"piapi.youget.job.{job}.pid"):
                rc.lrem('piapi.youget.jobs', 0, job)
            

scheduler = BackgroundScheduler()
scheduler.add_job(job, 'interval', hours=24)
scheduler.start()


async def run_command(command):
    process = await asyncio.create_subprocess_exec(*command,
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    
    stdout, stderr = await process.communicate()
    return stdout.decode(), stderr.decode()


async def run_command_no_wait(command) -> int:
    process = await asyncio.create_subprocess_exec(*command,
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    
    return str(process.pid)


class VideoStreams(BaseModel):
    container: str
    quality: str
    size: int
    src: List[Union[list, str]]


class VideoInfo(BaseModel):
    url: str
    title: Union[str, None] = None
    site: Union[str, None] = None
    streams: Union[Dict[str, VideoStreams], None] = None


class VideoJobIn(BaseModel):
    url: str
    status: Union[str, None] = None
    video_name: Union[str, None] = None
    pid: Union[str, None] = None
    format: Union[str, None] = None
    metadata: Union[str, None] = None
    uuid: Union[str, None] = None


class VideoJobOut(BaseModel):
    uuid: str
    url: str
    pid: str
    format: str
    status: str
    video_name: str
    metadata: str


class VideoJob(BaseModel):
    url: str
    status: Union[str, None] = None
    video_name: Union[str, None] = None
    pid: Union[str, None] = None
    format: Union[str, None] = None
    metadata: Union[str, None] = None
    uuid: Union[str, None] = None


@app.post("/api/youget/getinfo/", response_model=VideoInfo)
async def get_info(video_info: VideoInfo) -> VideoInfo:
    redis_conn = RedisConn()
    saved_job_uuid = redis_conn.get_job_uuid_with_url(video_info.url)
    if saved_job_uuid:
        video_info = VideoInfo(**redis_conn.get_job_metadata_dict(saved_job_uuid))
        return video_info

    cmd = ['you-get', '--json', video_info.url, 
           '-c', COOKIE_FILE]
    stdout, stderr = await run_command(cmd)
    metadata = stdout
    video_info = VideoInfo(**json.loads(stdout))

    job_uuid = str(uuid.uuid4())
    
    redis_conn.set_job_with_ready(job_uuid=job_uuid, 
                                 video_name=video_info.title, 
                                 url=video_info.url, 
                                 metadata=metadata)

    return video_info


@app.post("/api/youget/download/", response_model=VideoJobOut)
async def download(video_job: VideoJobIn) -> Any:
    redis_conn = RedisConn()

    if not video_job.uuid:
        video_job.uuid = redis_conn.get_job_uuid_with_url(video_job.url)

    if not video_job.format:
        vi = VideoInfo(**redis_conn.get_job_metadata_dict(video_job.uuid))
        size = 0
        for k, stream in vi.streams.items():
            if stream.size > size:
                video_job.format = k
                size += stream.size
                # TODO work out a better way the best quality.

    video_job_dict = video_job.model_dump()
    video_job_dict.update(redis_conn.get_job_with_uuid(video_job.uuid))

    pid = await run_command_no_wait(['you-get', '-o', DOWNLOAD_DIR, 
                                        f"--format={video_job.format}", 
                                        video_job.url, 
                                        '-c', COOKIE_FILE])

    redis_conn.set_job_with_downloading(video_job.uuid)
    redis_conn.set_job_pid(video_job.uuid, pid)
    video_job_dict.update({
        'status': JOB_SIG_DOWNLOADING,
        'pid': pid
    })

    return VideoJobOut(**video_job_dict)


@app.get("/api/youget/listall/")
async def list_all():
    redis_conn = RedisConn()
    redis_conn.update_jobs_status()
    return {uuid: job for uuid, job in redis_conn.get_jobs_to_inte_dict(
        retuuid=True, nometadata=True
    )}


@app.get("/api/youget/list/{uuid}")
async def list(uuid: Union[UUID4, None] = None):
    redis_conn = RedisConn()
    redis_conn.update_job_status(uuid)
    job = redis_conn.get_job_with_uuid(uuid)
    return {'jobs': {uuid: job}}


@app.get("/")
async def root():
    return RedirectResponse(url='/docs/', status_code=303)
