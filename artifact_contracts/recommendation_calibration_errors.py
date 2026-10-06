"""推薦校準輸出的純錯誤契約；不載入模型或訓練服務。"""


class InvalidCalibrationOutputError(ValueError):
    """校準器輸出不是有限的合法機率，不能轉成公開 basis points。"""
