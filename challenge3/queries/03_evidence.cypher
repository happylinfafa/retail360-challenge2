
MATCH (c:Customer)-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(l:OrderLine)-[:OF_PRODUCT]->(p:Product {stockCode:$product})
MATCH (l)-[:DERIVED_FROM]->(s:DataSource)
RETURN c.customerId AS customer,i.invoiceId AS invoice,toString(i.invoiceDate) AS date,
p.stockCode AS product,l.quantity AS quantity,l.rowId AS sourceRow,s.fileName AS file
ORDER BY customer,date
