# GPU Setup Guide for PyTorch

If you want to use **GPU acceleration** with PyTorch, follow these steps:

---

## 1. Install CUDA Drivers
You need an **NVIDIA Graphics Card** and the corresponding CUDA Toolkit.  
👉 Download here: [CUDA Downloads](https://developer.nvidia.com/cuda-downloads)

Validate your installation by running in CMD:

```bash
nvcc --version
nvidia-smi
```

---

## 2. Uninstall Existing Torch

Remove any previous CPU-only PyTorch installations:

```bash
pip uninstall torch torchvision torchaudio -y
```

---

## 3. Reinstall Torch with CUDA Support

Use the [official PyTorch installation guide](https://pytorch.org/get-started/locally/) to find the right command for your CUDA version.

For example, since my CUDA is **12.9**, I installed with:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu129
```

---

## 4. Validate GPU Availability

Run the following test in Python:

```python
import torch

print("CUDA available:", torch.cuda.is_available())
print("Current device:", torch.cuda.current_device() if torch.cuda.is_available() else "CPU")
print("Device name:", torch.cuda.get_device_name(torch.cuda.current_device()) if torch.cuda.is_available() else "CPU")
```

If everything is set up correctly, you should see the name of your NVIDIA GPU.

---

## ⚠️ Troubleshooting

Here are some common issues and fixes:

### 🔹 `torch.cuda.is_available()` returns `False`

* Your NVIDIA drivers may be outdated → [Update drivers](https://www.nvidia.com/Download/index.aspx).
* CUDA Toolkit version doesn’t match the installed PyTorch build.
  Example: If you installed `cu129` but your drivers only support CUDA 12.2, you’ll get `False`.
  👉 Run `nvidia-smi` to check the **driver-supported CUDA version**.

### 🔹 `nvcc` not found

* CUDA Toolkit is not in your PATH. Add this to your environment variables:

  ```bash
  export PATH=/usr/local/cuda/bin:$PATH
  export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
  ```

  (For Windows, add `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\vXX.X\bin` to the system PATH.)

### 🔹 `nvidia-smi` not found

* NVIDIA drivers are not installed properly. Reinstall from [NVIDIA Drivers](https://www.nvidia.com/Download/index.aspx).

### 🔹 Python environment conflicts

* Make sure you’re using a clean environment (e.g., `venv` or `conda`) to avoid version clashes.
* Sometimes you need to uninstall and reinstall again:

  ```bash
  pip uninstall torch torchvision torchaudio -y
  pip cache purge
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cuXXX
  ```
