
MATCH (a:Customer {customerId:$customer})-[:PLACED]->(i:Invoice)-[:HAS_LINE]->(:OrderLine)-[:OF_PRODUCT]->(p:Product)
WHERE i.invoiceDate >= localdatetime($start) AND i.invoiceDate < localdatetime($end)
WITH a, collect(DISTINCT p.stockCode) AS aProducts
MATCH (b:Customer)-[:PLACED]->(j:Invoice)-[:HAS_LINE]->(:OrderLine)-[:OF_PRODUCT]->(q:Product)
WHERE b <> a AND j.invoiceDate >= localdatetime($start) AND j.invoiceDate < localdatetime($end)
WITH a,b,aProducts,collect(DISTINCT q.stockCode) AS bProducts
WITH a,b,aProducts,bProducts,[x IN aProducts WHERE x IN bProducts] AS shared
RETURN a.customerId AS customer, b.customerId AS other,
size(aProducts) AS productsA,size(bProducts) AS productsB,shared,
toFloat(size(shared))/(size(aProducts)+size(bProducts)-size(shared)) AS jaccard
ORDER BY jaccard DESC,other
