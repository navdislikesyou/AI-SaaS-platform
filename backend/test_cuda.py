import sys
import torch

print("=" * 50)
print("Python:", sys.executable)
print("Torch:", torch.__version__)
print("Torch CUDA:", torch.version.cuda)
print("CUDA Available:", torch.cuda.is_available())
print("CUDA Device Count:", torch.cuda.device_count())

try:
    print("GPU Name:", torch.cuda.get_device_name(0))
except Exception as e:
    print("GPU Error:", e)

print("=" * 50)