import os
import sys

conda_root = os.path.dirname(sys.executable)
print(f"Conda root: {conda_root}\n")

# Search in common locations
search_paths = [
    conda_root,
    os.path.join(conda_root, 'Library', 'bin'),
    os.path.join(conda_root, 'Library', 'lib'),
    os.path.join(conda_root, 'DLLs'),
]

target_files = ['tcl86t.dll', 'tk86t.dll', 'tcl86.dll', 'tk86.dll']

for search_path in search_paths:
    if not os.path.exists(search_path):
        continue
    print(f"Searching in: {search_path}")
    try:
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.lower() in [t.lower() for t in target_files]:
                    full_path = os.path.join(root, file)
                    size = os.path.getsize(full_path)
                    print(f"  Found: {file} at {full_path} ({size:,} bytes)")
    except Exception as e:
        print(f"  Error: {e}")
    print()
