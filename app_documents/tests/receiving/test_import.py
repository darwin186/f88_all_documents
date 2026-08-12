from io import BytesIO

import pandas as pd
from django.test import SimpleTestCase

from app_documents.views import _load_receiving_import_df, _pick_date_columns


RECEIVING_COLUMNS = [
    "Ngày nhận thực tế Ngày",
    "Ngày nhận thực tế Tháng",
    "Ngày nhận thực tế Năm",
    "PGD",
    "Ngày phát sinh chứng từ Ngày",
    "Ngày phát sinh chứng từ Tháng",
    "Ngày phát sinh chứng từ Năm",
    "Loại chứng từ",
    "Mã thùng F88",
    "Nhân sự",
    "Folder type",
]

RECEIVING_ROW = [
    30,
    7,
    2026,
    "HNI25137.115 Trần Cung",
    29,
    7,
    2026,
    "Chứng từ Vận hành hằng ngày",
    "VH-260730-101",
    "datnm",
    "1",
]


def _excel_file(startrow=0):
    output = BytesIO()
    pd.DataFrame([RECEIVING_ROW], columns=RECEIVING_COLUMNS).to_excel(
        output,
        index=False,
        startrow=startrow,
    )
    output.seek(0)
    return output


class ReceivingImportExcelTests(SimpleTestCase):
    def test_reads_header_on_first_row_without_losing_only_data_row(self):
        dataframe = _load_receiving_import_df(_excel_file(startrow=0))

        self.assertEqual(len(dataframe.index), 1)
        self.assertEqual(dataframe.iloc[0]["Mã thùng F88"], "VH-260730-101")

    def test_reads_header_on_second_row(self):
        dataframe = _load_receiving_import_df(_excel_file(startrow=1))

        self.assertEqual(len(dataframe.index), 1)
        self.assertEqual(dataframe.iloc[0]["Nhân sự"], "datnm")

    def test_recognizes_full_date_column_names_from_ui_template(self):
        date_columns = _pick_date_columns(RECEIVING_COLUMNS)

        self.assertEqual(date_columns["receive_day"], "Ngày nhận thực tế Ngày")
        self.assertEqual(date_columns["receive_month"], "Ngày nhận thực tế Tháng")
        self.assertEqual(date_columns["receive_year"], "Ngày nhận thực tế Năm")
        self.assertEqual(date_columns["folder_day"], "Ngày phát sinh chứng từ Ngày")
        self.assertEqual(date_columns["folder_month"], "Ngày phát sinh chứng từ Tháng")
        self.assertEqual(date_columns["folder_year"], "Ngày phát sinh chứng từ Năm")
