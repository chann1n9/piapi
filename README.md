# Piapi

## User Guide

### Install Requirements

`pip install -r requirements.txt`

### Redis

I used to start a Redis service with Docker. You can use your own preferred method. In any case, Piapi needs a Redis service to store data.

`docker run --name piapi_redis -p 6379:6379 -d redis`

### Start Piapi

You need to configure the environment variables according to your own configuration. Here is an example.

```bash
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6379
# export REDIS_PASSWORD=
export DOWNLOAD_DIR=/path/to/download/videos
export COOKIE_FILE=/path/to/cookies_file

uvicorn app.main:app --host=0.0.0.0
```

`REDIS_PASSWORD` is not required. If you don’t need it, you can skip configuring it.

### Test

Try to Access [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.
If everything goes well, you will see the API documentation in your browser.

### Run Piapi in Docker

dockerfile

```dockerfile
FROM python:3.9

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY ./app /code/app

VOLUME [ "/data" ]

RUN cp /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list.d/debian.sources.bak
RUN sed -i 's#http://deb.debian.org#https://mirrors.tuna.tsinghua.edu.cn#g' /etc/apt/sources.list.d/debian.sources
RUN sed -i '/Signed-By/ atrusted: yes' /etc/apt/sources.list.d/debian.sources
RUN apt update && apt install -y ffmpeg

ENV REDIS_HOST=127.0.0.1
ENV REDIS_PORT=6389
# ENV REDIS_PASSWORD
ENV DOWNLOAD_DIR=/data
ENV COOKIE_FILE=/data/cookies.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
```

You need to modify REDIS_HOST and REDIS_PORT according to your own Redis configuration like

```dockerfile
ENV REDIS_HOST=Your.Redis.Host.Address
ENV REDIS_PORT=Your.Redis.Host.Port
```

As mentioned above. REDIS_PASSWORD is optional.

Then build

`docker build -t piapi:1.0 .`

If there is no error, you can start the container next.

`docker run --name piapi -p 8000:80 -v /path/to/download/videos:/data piapi:1.0`

I ran piapi on port 8000 of the host. You can modify it according to your needs, or even configure Nginx for it.

**You can see that when running in Docker, my cookies and videos are stored in the same path. I haven’t optimized it yet, so I can only do it this way for now.**

#### IP Address Of Your Redis In Docker

If you start Redis as I described above, then its default network mode is bridge.

`docker network inspect bridge`


```bash
...
"Containers": {
...
    "c281674df3cc1f8b6f88efa1dcf2c8b3199c6b293c6dac3f0d4167b4b75a105e": {
        "Name": "piapi_redis",
        "EndpointID": ...,
        "MacAddress": ...,
        "IPv4Address": "172.17.0.3/16",
        "IPv6Address": ""
    },
    ...
},
...
```

So the IP Address of your redis is 172.17.0.3

#### About Source Of Pip And Apt

As you can see, I replaced the pip source and apt source. This is to build image faster in China. If you want to get them from the official source, you can remove the -i parameter in the pip command and delete the lines with cp and sed commands.
