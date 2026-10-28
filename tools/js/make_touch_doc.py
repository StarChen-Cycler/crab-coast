from PIL import Image
import os
src = r"C:\Users\LENOVO\.dsh\attachments\v1\objects\bc\bca40e676ff2c26b48a65d835c6e574809272d15adea8411233e8119446f6fa1"
im = Image.open(src).convert("RGB")
q = im.quantize(colors=160, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
q.save("docs/touch_controls.png", optimize=True)
print("docs/touch_controls.png", q.size, round(os.path.getsize("docs/touch_controls.png")/1024), "KB")