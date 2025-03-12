import openpyxl


def create_xls(columns, data, file_name="signals.xlsx"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active

    # Запись заголовков
    for col_num, column_name in enumerate(columns, start=1):
        sheet.cell(row=1, column=col_num, value=column_name)

    # Запись данных
    for row_num, row_data in enumerate(data, start=2):
        for col_num, cell_value in enumerate(row_data, start=1):
            sheet.cell(row=row_num, column=col_num, value=cell_value)

    workbook.save(file_name)
    return file_name

def create_xls_stat(columns, data, file_name="orders_stat.xlsx"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active

    # Запись заголовков
    for col_num, column_name in enumerate(columns, start=1):
        sheet.cell(row=1, column=col_num, value=column_name)

    # Запись данных
    for row_num, row_data in enumerate(data, start=2):
        for col_num, cell_value in enumerate(row_data, start=1):
            sheet.cell(row=row_num, column=col_num, value=cell_value)

    workbook.save(file_name)
    return file_name
