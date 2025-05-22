from osgeo import gdal
import os

# リファレンスTIF（空間解像度・位置合わせ基準）
model_tif = "/media/hina/AE60-1503/sabo_UNet_Planet_trial05/01_inputLayers_all/clipped_unresampled/clipped_diff_normalized_planet_akatani.tif"

# ベースディレクトリ（入力・出力）
base_dir = "/media/hina/AE60-1503/sabo_UNet_Planet_trial05/01_inputLayers_all/clipped_unresampled"

# 処理する地域名リスト（必要な分だけ追加OK）
locations = ["iburi", "gofukuya", "noto", "akatani"]  # ←ここに対象地域名を追加してね

# 処理するタイプ（マスクとDEM）
targets = ["mask", "dem"]

# リファレンス画像から情報取得
model_ds = gdal.Open(model_tif)
geo_transform = model_ds.GetGeoTransform()
projection = model_ds.GetProjection()
cols = model_ds.RasterXSize
rows = model_ds.RasterYSize
model_ds = None

# 各地域・各ファイルタイプを処理
for loc in locations:
    for t in targets:
        input_tif = os.path.join(base_dir, f"clipped_{t}_{loc}.tif")
        output_tif = os.path.join(base_dir, f"clipped_resampled_{t}_{loc}.tif")
        os.makedirs(os.path.dirname(output_tif), exist_ok=True)

        if not os.path.exists(input_tif):
            print(f"❌ 入力ファイルが見つかりません: {input_tif}")
            continue

        print(f"Resampling: {os.path.basename(input_tif)} ...")

        gdal.Warp(
            destNameOrDestDS=output_tif,
            srcDSOrSrcDSTab=input_tif,
            format='GTiff',
            outputBounds=(
                geo_transform[0],
                geo_transform[3] + geo_transform[5] * rows,
                geo_transform[0] + geo_transform[1] * cols,
                geo_transform[3]
            ),
            xRes=geo_transform[1],
            yRes=abs(geo_transform[5]),
            dstSRS=projection,
            resampleAlg='near',
            warpOptions=["INIT_DEST=2"] if t == "mask" else None,
            multithread=True
        )

        print(f"✅ Saved: {output_tif}")

