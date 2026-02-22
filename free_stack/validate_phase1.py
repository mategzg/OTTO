#!/usr/bin/env python3
import os
import tempfile
import urllib.request
from pathlib import Path

print("[1/3] Qdrant check...")
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

q = QdrantClient(url="http://127.0.0.1:6333", timeout=10)
print("health:", q.get_collections().collections is not None)
q.recreate_collection("phase1_demo", vectors_config=VectorParams(size=4, distance=Distance.COSINE))
q.upsert(
    collection_name="phase1_demo",
    points=[
        PointStruct(id=1, vector=[0.9, 0.1, 0.0, 0.0], payload={"txt": "hola"}),
        PointStruct(id=2, vector=[0.1, 0.9, 0.0, 0.0], payload={"txt": "adios"}),
    ],
)
r = q.search(collection_name="phase1_demo", query_vector=[1.0, 0.0, 0.0, 0.0], limit=1)
print("top result:", r[0].payload)

print("[2/3] OCR check (RapidOCR)...")
from PIL import Image, ImageDraw
from rapidocr_onnxruntime import RapidOCR

with tempfile.TemporaryDirectory() as td:
    imgp = Path(td) / "ocr_test.png"
    img = Image.new("RGB", (900, 220), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((30, 80), "OTTO OCR local OK", fill=(0, 0, 0))
    img.save(imgp)

    ocr = RapidOCR()
    res, _ = ocr(str(imgp))
    txt = " ".join([x[1] for x in (res or [])])
    print("ocr output:", txt if txt else "(vacio)")

print("[3/3] STT check (faster-whisper)...")
from faster_whisper import WhisperModel

with tempfile.TemporaryDirectory() as td:
    ap = Path(td) / "jfk.flac"
    urllib.request.urlretrieve(
        "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac", ap
    )
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(ap), language="en")
    text = " ".join([s.text.strip() for s in segments])
    print("detected language:", info.language)
    print("stt sample:", text[:140])

print("\nPHASE1_VALIDATION_OK")
