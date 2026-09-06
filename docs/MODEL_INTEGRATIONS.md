# Local Model Integration

`SithAssembly//SignalForge` and `SithAssembly//GlyphWatch` are optional adapters. The core system runs without ML dependencies and never installs packages or fetches weights silently.

## Selected Profiles

- Comment outliers: PyOD ECOD is the primary option. It scores transparent, local features such as text length, capitalization, punctuation, links, mentions, hashtags, and duplicate text. With fewer than 20 comments, SignalForge uses a robust local baseline. Every result remains `review_required`.
- Screenshot OCR: GlyphWatch uses the PP-OCRv6 small detector and recognizer through PaddleOCR's Transformers backend. The combined profile has 7.7 million parameters, supports 50 languages, and is suitable for desktop use. Its editable definition is in `config/embedded_model_registry.json`; Hugging Face and PaddleX runtime caches are both placed under `.runtime` and are not committed.
- Relative depth: GlyphWatch uses the locally pinned `depth-anything/Depth-Anything-V2-Small-hf` snapshot for opt-in relative-depth derivatives of explicit local image evidence. It creates a 16-bit grayscale PNG beside the source evidence and records the repository, revision, model profile, source size, artifact hash, and timestamp. The output is a comparison feature, not a distance measurement.
- Document-focused alternative: docTR is appropriate when PDFs or multi-page documents become the primary source format. It is intentionally not enabled as a second OCR adapter, avoiding duplicate model downloads and inconsistent result formats.

## Setup

For SignalForge after explicit approval:

```powershell
python -m pip install numpy pyod
```

For GlyphWatch's local Hugging Face / PyTorch backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-glyphwatch.txt
```

Install a CUDA-enabled PyTorch wheel separately when GPU inference is required. The PP-OCRv6 small assets are preloaded only when `hf download` is run explicitly; an OCR request never installs dependencies. The runtime pins Hugging Face and PaddleX caches to project-local directories through `HF_HOME` and `PADDLE_PDX_CACHE_HOME`.

Depth Anything V2 Small is downloaded explicitly into `.runtime/models/Depth-Anything-V2-Small-hf` and loaded with `local_files_only=True`. Its registry entry pins the Hugging Face revision. A depth request requires `confirm_depth_analysis: true` and never fetches weights at request time.

This workstation already has the matching CPU package pair `torch 2.9.1` and `torchvision 0.24.1`. To switch that existing pair to the NVIDIA CUDA 13.0 build, use this explicit replacement command after stopping local Python processes:

```powershell
python -m pip install --upgrade --force-reinstall torch==2.9.1+cu130 torchvision==0.24.1+cu130 --index-url https://download.pytorch.org/whl/cu130
```

Verify the result with `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`. Do not install xFormers until the CUDA-enabled PyTorch build is working; it is not needed for PP-OCRv6 small.

`RUN.bat` automatically uses `.venv\\Scripts\\python.exe` when the project environment exists. The virtual environment and pip cache remain on the project drive and are excluded from Git.

## Private Model Mirror

Approved local model snapshots are mirrored to the private Hugging Face bucket `Lennox9898/sithassembly-model-store`. The human-editable allowlist in `config/model_mirror_registry.json` records the source repository, immutable revision, license, local directory, and bucket destination for every model. `tools/Sync-ModelBucket.ps1` previews the upload by default and performs it only with `-Apply`.

The bucket is for approved model snapshots and non-sensitive model evaluation artifacts. It is not a mirror of the GitHub source repository and must never contain case evidence, credentials, databases, vault files, agent reports, or general project files. See `docs/HF_MODEL_BUCKET.md` for the test-Space boundary and sync process.

## Limits

- Anomaly scores are not findings about intent, ideology, identity, or coordination.
- OCR output is stored as a derived result with evidence ID, model profile, and timestamp. The unchanged local image remains referenceable.
- Depth output is stored as a 16-bit relative-depth derivative. It is included in encrypted evidence vaults together with its run record and does not provide metric distance values.
- Only explicitly uploaded local images are processed. No URLs are fetched and no platforms are crawled.

## Primary Sources

- PaddleOCR PP-OCRv6 small detector: https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_safetensors
- PaddleOCR PP-OCRv6 small recognizer: https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_safetensors
- PaddleOCR PP-OCRv6 model family: https://huggingface.co/blog/paddlepaddle/pp-ocrv6
- Depth Anything V2 Small: https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf
- Depth Anything V2 source and license: https://github.com/DepthAnything/Depth-Anything-V2
- PyTorch Windows installation: https://pytorch.org/get-started/locally/
- PyOD ECOD: https://github.com/yzhao062/pyod/blob/master/pyod/models/ecod.py
