import asyncio
import asyncpg
from config import DATABASE_URI

async def check():
    kwargs = {"statement_cache_size": 0} if ("supabase" in DATABASE_URI or "pooler" in DATABASE_URI or ":6543" in DATABASE_URI) else {}
    conn = await asyncpg.connect(DATABASE_URI, **kwargs)

    print("=== Loan disbursement by month (latest 10) ===")
    rows = await conn.fetch("""
        SELECT DATE_TRUNC('month', date)::date as month, COUNT(*) as cnt, SUM(principle_amount) as total
        FROM loan_data
        GROUP BY 1 ORDER BY 1 DESC LIMIT 10
    """)
    for r in rows:
        print(f"  {r['month']}  loans={r['cnt']}  total={r['total']}")

    print("\n=== Collections by month (latest 10) ===")
    rows2 = await conn.fetch("""
        SELECT DATE_TRUNC('month', date)::date as month, COUNT(*) as cnt, SUM(amountpaid) as total
        FROM statement WHERE transactiontype IN ('addColl','writeoff')
        GROUP BY 1 ORDER BY 1 DESC LIMIT 10
    """)
    for r in rows2:
        print(f"  {r['month']}  txns={r['cnt']}  total={r['total']}")

    print("\n=== Performance summary for current year (2026) ===")
    import datetime
    start = datetime.date(datetime.date.today().year, 1, 1)
    end = datetime.date.today()
    print(f"  Date range: {start} to {end}")

    val = await conn.fetchval(
        "SELECT SUM(principle_amount) FROM loan_data WHERE DATE(date) BETWEEN $1 AND $2", start, end
    )
    print(f"  Disbursed this year: {val}")

    val2 = await conn.fetchval(
        "SELECT SUM(amountpaid) FROM statement WHERE DATE(date) BETWEEN $1 AND $2 AND transactiontype IN ('addColl','writeoff')", start, end
    )
    print(f"  Collected this year: {val2}")

    print("\n=== Sample loan dates (most recent 5) ===")
    sample = await conn.fetch("SELECT loan_number, date, principle_amount FROM loan_data ORDER BY date DESC LIMIT 5")
    for r in sample:
        print(f"  {r['loan_number']}  {r['date']}  {r['principle_amount']}")

    await conn.close()

asyncio.run(check())
