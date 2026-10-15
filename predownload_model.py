# predownload_model.py
"""预先下载 pyturboocr 模型（单进程，避免冲突）"""
import os
import tempfile

os.environ["PYTHONWARNINGS"] = "ignore"

print("开始下载 pyturboocr 模型（约 60~120MB，请等待）...")

try:
    from pyturboocr import OCR
    import numpy as np
    from PIL import Image

    print("1. 初始化引擎...")
    ocr = OCR(
        tier="small",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    print("✅ 引擎初始化成功")

    # 强制触发模型加载（用一张小图测试）
    test_img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    tmp = os.path.join(tempfile.gettempdir(), "_pyturboocr_test.jpg")
    Image.fromarray(test_img).save(tmp)
    print(f"   测试图已保存: {tmp}")

    print("2. 测试识别（会加载检测模型 + 识别模型）...")
    result = ocr.recognize_image(tmp)
    print(f"✅ 模型加载完成")
    print(f"   识别结果: {result}")

    print("\n🎉 全部就绪！可以启动 GUI 程序了。")

except Exception as e:
    import traceback
    print(f"\n❌ 失败: {e}")
    print("完整错误信息：")
    traceback.print_exc()