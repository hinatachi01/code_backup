# -*- coding:utf-8 -*-

import sys
import zipfile
import numpy as np
import xml.etree.ElementTree as et
from osgeo import gdal, osr

def convert(input_filename, output_filename):
    ns = {
        'ns': 'http://fgd.gsi.go.jp/spec/2008/FGD_GMLSchema',
        'gml': 'http://www.opengis.net/gml/3.2',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xlink': 'http://www.w3.org/1999/xlink'
    }

    nodata = -9999  # nodata値
    dataset = []
    mllon, mllat, mulon, mulat = 180, 90, -180, -90

    # ピクセルサイズ候補のリストを入れておく（例: タイル内の最小ピクセルサイズ）
    pixelx_list = []
    pixely_list = []

    with zipfile.ZipFile(input_filename, 'r') as zf:
        filelist = zf.namelist()
        for filename in filelist:
            if not filename.endswith('.xml'):
                continue
            print('loading ' + filename)
            with zf.open(filename, 'r') as file:
                text = file.read().decode('utf_8')
                root = et.fromstring(text)
                dem = root.find('ns:DEM', ns)
                if dem is None:
                    print('DEMタグが見つかりません')
                    continue
                coverage = dem.find('ns:coverage', ns)
                if coverage is None:
                    print('coverageタグが見つかりません')
                    continue
                envelope = coverage.find('gml:boundedBy//gml:Envelope', ns)
                if envelope is None:
                    print('Envelopeタグが見つかりません')
                    continue
                lower = envelope.find('gml:lowerCorner', ns).text
                upper = envelope.find('gml:upperCorner', ns).text

                grid = coverage.find('gml:gridDomain//gml:Grid//gml:limits//gml:GridEnvelope', ns)
                low = grid.find('gml:low', ns).text
                high = grid.find('gml:high', ns).text

                tuplelist = coverage.find('gml:rangeSet//gml:DataBlock//gml:tupleList', ns).text.strip()

                gridfunc = coverage.find('gml:coverageFunction//gml:GridFunction', ns)
                rule = gridfunc.find('gml:sequenceRule', ns)
                start = gridfunc.find('gml:startPoint', ns).text

                if rule.attrib.get('order', '') != '+x-y':
                    print('warning: sequence order not +x-y')
                if rule.text != 'Linear':
                    print('warning: sequence rule not Linear')

                s = np.array(lower.split(' '), dtype=np.float64)
                llat, llon = s[0], s[1]
                if llat < mllat: mllat = llat
                if llon < mllon: mllon = llon

                s = np.array(upper.split(' '), dtype=np.float64)
                ulat, ulon = s[0], s[1]
                if ulat > mulat: mulat = ulat
                if ulon > mulon: mulon = ulon

                s = low.split(' ')
                lowx, lowy = int(s[0]), int(s[1])
                s = high.split(' ')
                highx, highy = int(s[0]), int(s[1])

                datapoints = tuplelist.splitlines()

                xsize = highx - lowx + 1
                ysize = highy - lowy + 1

                # タイル内のピクセルサイズを計算（度）
                tile_lon_width = ulon - llon
                tile_lat_height = ulat - llat
                pixel_x_size = tile_lon_width / xsize
                pixel_y_size = tile_lat_height / ysize

                pixelx_list.append(pixel_x_size)
                pixely_list.append(pixel_y_size)

                raster = np.full((ysize, xsize), nodata, dtype=np.float32)

                s = start.split(' ')
                x, y = int(s[0]), int(s[1])

                for datapoint in datapoints:
                    s = datapoint.split(',')
                    if len(s) < 2:
                        continue
                    desc, value = s[0], s[1]
                    try:
                        val = float(value)
                    except:
                        val = nodata

                    if desc == '地表面':
                        raster[y][x] = val
                    else:
                        if desc == 'その他' and val == -9999:
                            raster[y][x] = nodata
                        else:
                            raster[y][x] = val

                    x += 1
                    if x > highx:
                        x = 0
                        y += 1
                        if y > highy:
                            break

                data = {
                    'llat': llat,
                    'llon': llon,
                    'ulat': ulat,
                    'ulon': ulon,
                    'xsize': xsize,
                    'ysize': ysize,
                    'raster': raster
                }
                dataset.append(data)

    if len(dataset) == 0:
        print(f'{input_filename} : データセットがありませんでした。処理を終了します。')
        return

    # 最小のピクセルサイズを使う（最も高解像度のタイルに合わせる）
    pixelx = min(pixelx_list)
    pixely = min(pixely_list)

    print(f"使用するピクセルサイズ（度）: 経度 {pixelx}, 緯度 {pixely}")

    # 全体のピクセル数を計算（範囲 ÷ ピクセルサイズ）
    total_width = int(round((mulon - mllon) / pixelx))
    total_height = int(round((mulat - mllat) / pixely))

    print(f"出力画像サイズ: 幅 {total_width} px, 高さ {total_height} px")

    merged_raster = np.full((total_height, total_width), nodata, dtype=np.float32)

    for data in dataset:
        # 各タイルの左上座標からオフセット算出
        offset_x = int(round((data['llon'] - mllon) / pixelx))
        offset_y = int(round((mulat - data['ulat']) / pixely))
        ysize, xsize = data['raster'].shape

        # 書き込み範囲を計算し、範囲内かチェック
        end_x = offset_x + xsize
        end_y = offset_y + ysize
        if end_x > total_width or end_y > total_height:
            print(f"警告: タイルが出力範囲を超えています。調整が必要です。")

        merged_raster[offset_y:end_y, offset_x:end_x] = data['raster']

    trans = [mllon, pixelx, 0, mulat, 0, -pixely]

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(6668)

    driver = gdal.GetDriverByName('GTiff')
    output = driver.Create(output_filename, total_width, total_height, 1, gdal.GDT_Float32)
    output.GetRasterBand(1).WriteArray(merged_raster)
    output.GetRasterBand(1).SetNoDataValue(nodata)
    output.SetGeoTransform(trans)
    output.SetProjection(srs.ExportToWkt())
    output.FlushCache()

    print(f"GeoTIFFを作成しました: {output_filename}")

def main(argv):
    if len(argv) < 2:
        print("使い方: python convert_xml_to_tif.py input1.zip [input2.zip ...]")
        return
    for input_zip in argv[1:]:
        output_tif = input_zip.replace('.zip', '.tif')
        print(f'処理中: {input_zip}')
        convert(input_zip, output_tif)

if __name__ == '__main__':
    main(sys.argv)

