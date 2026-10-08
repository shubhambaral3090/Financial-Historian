"""Excel views of the shared analysis graph, with inspectable formulas and caches."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from decimal import Decimal

from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from .analysis import Analysis, Datum, currency


def append_analysis(workbook, bundle, analysis: Analysis) -> dict:
    from .export import (_base_sheet, _headers, _write_text, _style_row,
                         _source_link, _MUTED_FONT, _HEADER_FILL, _HEADER_FONT)
    cache = {}
    company = bundle.company.name
    inputs = _base_sheet(workbook,"Calculation Inputs",company,"Unscaled calculation graph · source facts and intermediate formulas",15)
    _headers(inputs,["ID","Description","Period","Unit","Value / formula","Status","Explanation",
                     "Source tag","Original label","Accession","Filed","Source URL","Context","Dimensions","Source decimals"])
    input_rows = {}
    next_row = 5

    def write_formula(sheet,cell,formula,value):
        cell.value = "=" + formula
        cache.setdefault(sheet.title,{})[cell.coordinate] = str(value)

    def register(item: Datum):
        nonlocal next_row
        # Keep strong references through the graph; identity avoids expensive
        # recursive dataclass hashing for multi-period decompositions.
        if id(item) in input_rows:
            return input_rows[id(item)]
        dependencies = [register(a) for a in item.inputs]
        row = next_row
        next_row += 1
        input_rows[id(item)] = row
        fact = item.fact
        values = [f"I{row-4}",item.label,item.period,item.unit,None,
                  "available" if item.value is not None else "unavailable",item.reason,
                  fact.tag if fact else "",fact.label if fact else "",
                  fact.accession if fact else "",fact.filed if fact else "",
                  fact.source_url if fact else "",fact.context_id if fact else "",
                  "; ".join(f"{a}={m}" for a,m in fact.dimensions) if fact else "",
                  fact.decimals if fact else ""]
        _style_row(inputs,row,15)
        for col,value in enumerate(values,1):
            if value is not None:
                _write_text(inputs.cell(row,col),value)
        cell = inputs.cell(row,5)
        if item.value is not None:
            if item.formula:
                expression = item.formula.format(*(f"E{r}" for r in dependencies))
                write_formula(inputs,cell,expression,item.value)
            else:
                cell.value = float(item.value)
        _source_link(inputs.cell(row,12),fact.source_url if fact else "")
        explanation = item.reason or "Unscaled value. " + ("Source: " + fact.source_url if fact else "Inputs: " + ", ".join(f"E{r}" for r in dependencies))
        cell.comment = Comment(explanation,"Fishtorian")
        cell.number_format = '#,##0.##########;[Red](#,##0.##########);0'
        return row

    def matrix(title,rows):
        sheet = _base_sheet(workbook,title,company,"Historical only · currency in millions · missing cells carry explanations",max(2,len(analysis.periods)+1))
        _headers(sheet,["Metric / reported line",*analysis.periods])
        sheet.freeze_panes = "B5"
        sheet.column_dimensions["A"].width = 52
        row_number = 5
        previous = None
        for row in rows:
            group = row.definition.group
            if group != previous:
                for col in range(1,len(analysis.periods)+2):
                    cell = sheet.cell(row_number,col)
                    cell.fill = _HEADER_FILL
                    cell.font = _HEADER_FONT
                _write_text(sheet.cell(row_number,1),group)
                row_number += 1
                previous = group
            _style_row(sheet,row_number,len(analysis.periods)+1)
            unit = row.definition.unit
            _write_text(sheet.cell(row_number,1),row.definition.label + (f" [{unit} million]" if currency(unit) else f" [{unit}]" if unit != "currency" else " [reported currency million]"))
            for col,p in enumerate(analysis.periods,2):
                item = row.cells[p]
                ref = register(item)
                cell = sheet.cell(row_number,col)
                scale = Decimal(1000000) if currency(item.unit) else Decimal(1)
                if item.value is not None:
                    formula = f"'Calculation Inputs'!E{ref}" + ("/1000000" if scale != 1 else "")
                    # pp is stored as percentage points, unlike percent ratios.
                    if item.unit == "pp":
                        formula += "*100"
                    result = item.value / scale * (100 if item.unit == "pp" else 1)
                    write_formula(sheet,cell,formula,result)
                cell.number_format = '0.00%;[Red](0.00%);0.00%' if item.unit=="%" else '0.00" pp"' if item.unit=="pp" else '0.00"x"' if item.unit=="x" else '#,##0.00;[Red](#,##0.00);0.00'
                provenance = "\n".join(f"{f.label} | {f.value} {f.unit} | {f.accession} | {f.source_url}" for f in item.sources)
                note = f"{row.definition.formula}\nCalculation Inputs!E{ref}\n{row.definition.limitation}\n{item.reason}\n{provenance}"
                cell.comment = Comment(note[:32000],"Fishtorian")
                if item.fact:
                    _source_link(cell,item.fact.source_url)
                sheet.column_dimensions[get_column_letter(col)].width = 18
            row_number += 1
        if not rows:
            _write_text(sheet.cell(5,1),"No supported schedule observations. See Sources & Coverage.")
        sheet.sheet_view.showGridLines = False
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = "1:4"

    for title,rows in analysis.schedules.items():
        matrix(title,rows)
    matrix("Historical Ratios",[r for r in analysis.rows if r.definition.group!="Return bridge"])
    matrix("Return Bridge",[r for r in analysis.rows if r.definition.group=="Return bridge"])
    matrix("Common Size",analysis.common_size)
    inputs.freeze_panes = "E5"
    inputs.auto_filter.ref = f"A4:O{max(4,next_row-1)}"
    for col in range(1,16):
        inputs.column_dimensions[get_column_letter(col)].width = 55 if col in {2,7,9,12,14} else 22
    method = _base_sheet(workbook,"Methodology",company,"Fishtorian · historical methods and interpretation",9)
    _headers(method,["Metric","Group","Formula","Unit","Purpose","Applicability","Balance convention","Limitations","Reference"])
    for i,row in enumerate(analysis.rows,5):
        d = row.definition
        values = [d.label,d.group,d.formula,d.unit,d.purpose,
                  "Known nonfinancial SEC SIC" if d.industrial else "Where required compatible inputs exist",
                  "Two-point beginning/ending average where formula specifies average; consecutive annual periods",
                  d.limitation,d.reference]
        _style_row(method,i,9)
        for col,value in enumerate(values,1):
            _write_text(method.cell(i,col),value)
    for i,note in enumerate(analysis.notes,len(analysis.rows)+6):
        _write_text(method.cell(i,1),"Policy")
        _write_text(method.cell(i,3),note)
    for col in range(1,10):
        method.column_dimensions[get_column_letter(col)].width = 48
    checks = _base_sheet(workbook,"Validation",company,"Passed checks are not a financial audit; unavailable checks remain explicit",6)
    _headers(checks,["Period","Check","Status","Difference","Tolerance","Explanation"])
    for i,check in enumerate(analysis.checks,5):
        _style_row(checks,i,6)
        for col,value in enumerate([check.period,check.label,check.status,check.difference,check.tolerance,check.reason],1):
            if isinstance(value,Decimal):
                checks.cell(i,col).value = float(value)
            elif value is not None:
                _write_text(checks.cell(i,col),value)
    checks.column_dimensions["B"].width = 48
    checks.column_dimensions["F"].width = 100
    workbook.calculation = CalcProperties(calcId=191029,fullCalcOnLoad=True,forceFullCalc=True)
    return cache


def cache_formula_results(payload: bytes, workbook, cache: dict) -> bytes:
    """Write numeric cached results into OOXML, preserving actual Excel formulas.

    openpyxl writes formula <v> empty. The shared engine supplies deterministic
    values for data-only readers; Excel still recalculates on opening/editing.
    """
    output = BytesIO()
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    by_path = {f"xl/worksheets/sheet{i}.xml":cache[s.title]
               for i,s in enumerate(workbook.worksheets,1) if s.title in cache}
    with ZipFile(BytesIO(payload)) as source, ZipFile(output,"w",ZIP_DEFLATED) as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename in by_path:
                root = ET.fromstring(data)
                values = by_path[entry.filename]
                for cell in root.iter(ns+"c"):
                    coordinate = cell.get("r")
                    if coordinate in values and cell.find(ns+"f") is not None:
                        value = cell.find(ns+"v")
                        if value is None:
                            value = ET.SubElement(cell,ns+"v")
                        value.text = values[coordinate]
                data = ET.tostring(root,encoding="utf-8",xml_declaration=True)
            target.writestr(entry,data)
    return output.getvalue()
