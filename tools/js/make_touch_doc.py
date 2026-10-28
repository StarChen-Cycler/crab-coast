from PIL import Image
import os
src = r"C:\Users\LENOVO\.dsh\attachments\v1\objects\51\516e8a2b4d764243fac1a7e38f3e8a6dde87aa299372d7318c96990c45b30c3c"
im = Image.open(src).convert("RGB")
q = im.quantize(colors=160, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
q.save("docs/touch_controls.png", optimize=True)
print("docs/touch_controls.png", q.size, round(os.path.getsize("docs/touch_controls.png")/1024), "KB")