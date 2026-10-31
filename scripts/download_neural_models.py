"""Developer setup: resumable, checksum-verified local OCR model downloads."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "vendor/neural"
MODELS = [
    ("paddle/model.gguf", "PaddlePaddle/PaddleOCR-VL-1.6-GGUF", "511b09642bb324401f15f97cc23bc67e8f0a291d", "PaddleOCR-VL-1.6-GGUF.gguf", 935769056, "f3ae46ec885050acf4b3d31944431e1fd90d50664fb09126af4a3c050ba14ee8"),
    ("paddle/mmproj.gguf", "PaddlePaddle/PaddleOCR-VL-1.6-GGUF", "511b09642bb324401f15f97cc23bc67e8f0a291d", "PaddleOCR-VL-1.6-GGUF-mmproj.gguf", 881770560, "204d757d7610d9b3faab10d506d69e5b244e32bf765e2bab2d0167e65e0a058a"),
    ("lighton/model.gguf", "staghado/LightOnOCR-3-0.8B-GGUF", "fad751c3a09edf99d55931ed399c6ce7a90ea5fe", "model-Q4_K_M.gguf", 541903744, "bb57c9769af18d02f0bde4dd0840737cae170d7340cc0435eddcc36b443459df"),
    ("lighton/mmproj.gguf", "staghado/LightOnOCR-3-0.8B-GGUF", "fad751c3a09edf99d55931ed399c6ce7a90ea5fe", "mmproj-F16.gguf", 204986944, "101acc9466a587a615bbf7b29c0ecb6744e309363eba8b615fe3e09f5e1c5d5f"),
    ('rapid/PP-OCRv6_det_small.onnx', 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx', '', '', 9929594, '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'),
    ('rapid/PP-OCRv6_rec_medium.onnx', 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/rec/PP-OCRv6_rec_medium.onnx', '', '', 76629984, 'eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b'),
    ('rapid/arabic_PP-OCRv5_rec_mobile.onnx', 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/arabic_PP-OCRv5_rec_mobile.onnx', '', '', 8023828, 'c1192e632d0baa9146ae5b756a0e635e3dc63c1733737ebfd1629e87144e9295'),
    ('layout/pp_doc_layoutv3.onnx', 'https://www.modelscope.cn/models/RapidAI/RapidLayout/resolve/v1.2.0/onnx/pp_doc_layout/pp_doc_layoutv3.onnx', '', '', 130502330, '250dbad1dfb9e4983fab75e1bf5085cd56ec3f41d5c7d0f8623ec74856e7aa67'),
]
CHUNK = 1024 * 1024


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def part(job):
    relative, repo, revision, filename, size, expected, offset = job
    count = min(CHUNK, size - offset)
    destination = BASE / ".download" / relative / f"{offset:012d}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size == count:
        return
    url = repo if repo.startswith('https://') else f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
    for attempt in range(5):
        try:
            request = urllib.request.Request(url + f"?download=true&part={offset}&fresh={int(time.time())}",
                headers={"Range": f"bytes={offset}-{offset + count - 1}"})
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Model server did not honor the requested range")
                data = response.read(count + 1)
            if len(data) != count:
                raise ValueError("Incomplete model chunk")
            destination.write_bytes(data)
            return
        except Exception:
            if attempt == 4:
                raise
            time.sleep(min(15, 2 ** attempt))


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    missing = [entry for entry in MODELS if not (BASE / entry[0]).is_file() or digest(BASE / entry[0]) != entry[5]]
    jobs = [(*entry, offset) for entry in missing for offset in range(0, entry[4], CHUNK)]
    with ThreadPoolExecutor(max_workers=48) as pool:
        futures = [pool.submit(part, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            future.result()
            if index % 32 == 0 or index == len(futures):
                print(f"Verified download parts: {index}/{len(futures)}", flush=True)
    for entry in missing:
        relative, repo, revision, filename, size, expected = entry
        target = BASE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        assembling = target.with_suffix(".assembling")
        with assembling.open("wb") as output:
            for offset in range(0, size, CHUNK):
                output.write((BASE / ".download" / relative / f"{offset:012d}").read_bytes())
        if digest(assembling) != expected:
            raise ValueError(f"Checksum mismatch: {relative}")
        assembling.replace(target)
        print("Model ready:", relative, flush=True)
    (BASE / "models.json").write_text(json.dumps([
        dict(path=e[0], repository=e[1], revision=e[2], file=e[3], bytes=e[4], sha256=e[5])
        for e in MODELS], indent=2), encoding="utf-8")
    archive_path = BASE / "llama-cpu.zip"
    if not archive_path.exists():
        urllib.request.urlretrieve("https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-win-cpu-x64.zip", archive_path)
    if digest(archive_path) != '37b3efcf962847ca869745fd4ccf7f5e7e8dacfeff9fa3523b4ca8cdc66d632b':
        raise ValueError('Native runtime checksum mismatch')
    (BASE / 'rapid/ready.json').write_text(json.dumps({
        Path(e[0]).name: e[5] for e in MODELS if e[0].startswith('rapid/')}))
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            assert (BASE / "runtime" / entry.filename).resolve().is_relative_to((BASE / "runtime").resolve())
        archive.extractall(BASE / "runtime")


if __name__ == "__main__":
    main()
