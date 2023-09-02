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
ENV REDIS_PORT=6379
# ENV REDIS_PASSWORD
ENV DOWNLOAD_DIR=/data
ENV COOKIE_FILE=/data/cookies.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
