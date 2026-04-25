FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/runpod-volume/huggingface \
    MODEL_CACHE_DIR=/runpod-volume/huggingface \
    MODEL_ID=RunDiffusion/Juggernaut-XL

WORKDIR /app

COPY requirements-worker.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements-worker.txt

COPY handler.py .

CMD ["python", "-u", "handler.py"]
