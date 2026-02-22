# Fase Gratis 1 (local)

Componentes habilitados:
- STT local: `faster-whisper`
- OCR local: `rapidocr-onnxruntime` + `Tesseract/OCRmyPDF`
- Vector DB local: `Qdrant` (binario local)
- Automatización local: `n8n`
- Monitoreo local: `Prometheus + Loki + Promtail + Grafana`

## 1) Instalar + arrancar Qdrant
```bash
bash free_stack/start_qdrant.sh
```
(la primera vez descarga e instala Qdrant 1.7.4 en `tools/qdrant/`)

## 2) Validar todo
```bash
python3 free_stack/validate_phase1.py
```

## 3) Fase 2 (n8n + monitoreo)
### Instalar binarios de observabilidad
```bash
bash free_stack/install_phase2.sh
```

### Arrancar n8n
```bash
bash free_stack/start_n8n.sh
```

### Arrancar monitoreo
```bash
bash free_stack/start_monitoring.sh
```

Paneles:
- n8n: http://127.0.0.1:5678
- Prometheus: http://127.0.0.1:9090
- Loki: http://127.0.0.1:3100
- Grafana: http://127.0.0.1:3000  (login inicial: `admin` / `admin`)

## 4) Uso rápido
### Transcribir audio
```python
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.wav", language="es")
for s in segments:
    print(f"[{s.start:.2f}-{s.end:.2f}] {s.text}")
```

### OCR imagen
```python
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
res, _ = ocr("imagen.png")
print("\n".join([r[1] for r in (res or [])]))
```

### Qdrant
```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

c = QdrantClient(url="http://127.0.0.1:6333")
c.recreate_collection("demo", vectors_config=VectorParams(size=4, distance=Distance.COSINE))
```

## Nota OCR/Tesseract
Tesseract/OCRmyPDF requieren paquetes de sistema (apt) y sudo. Queda pendiente ese paso cuando des permiso sudo.
