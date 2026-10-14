
UNWIND $rows AS r
MERGE (s:DataSource {sourceId:r.sourceId})
SET s.fileName=r.SourceFile, s.worksheet=r.Worksheet,
    s.url='https://archive.ics.uci.edu/dataset/502/online+retail+ii'
MERGE (c:Customer {customerId:r.CustomerID})
MERGE (i:Invoice {invoiceKey:r.invoiceKey})
SET i.invoiceId=r.Invoice, i.invoiceDate=localdatetime(r.InvoiceDate), i.country=r.Country
MERGE (p:Product {stockCode:r.StockCode})
SET p.description=r.Description
MERGE (l:OrderLine {lineId:r.lineId})
SET l.quantity=r.Quantity, l.unitPriceGBP=r.Price, l.rowId=r.RowID,
    l.excelRow=r.ExcelRow, l.description=r.Description
MERGE (c)-[:PLACED]->(i)
MERGE (i)-[:HAS_LINE]->(l)
MERGE (l)-[:OF_PRODUCT]->(p)
MERGE (l)-[:DERIVED_FROM]->(s)
MERGE (i)-[:RECORDED_IN]->(s)
