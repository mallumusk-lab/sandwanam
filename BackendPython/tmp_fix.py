import sys
import os

file_path = 'main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Check if lines 344-368 match the problematic block
# Lines are 0-indexed, so 344 is 343, 368 is 367
print(f"Line 344: {repr(lines[343])}")
print(f"Line 369: {repr(lines[368])}")

if 'return {\n' in lines[343] and '# Branch Data Calculation\n' in lines[368]:
    new_lines = lines[:343] + lines[368:]
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Successfully fixed main.py")
else:
    print("Could not find the expected block at the specified lines.")
