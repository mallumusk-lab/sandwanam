import asyncio
import asyncpg
import re
from config import DATABASE_URI

async def migrate_particulars():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Connected to database.")
    
    rows = await conn.fetch("SELECT loan_number, particulars FROM loan_data")
    
    for row in rows:
        loan_number = row['loan_number']
        old_particulars = row['particulars']
        
        if not old_particulars:
            continue
            
        print(f"Processing {loan_number}: {old_particulars}")
        
        # Split by comma (handles both ", " and ",")
        items = [i.strip() for i in old_particulars.split(",")]
        new_items = []
        modified = False
        
        for item in items:
            # Check for "Qty Name" format (legacy)
            legacy_match = re.match(r"^(\d+)\s+(.+)$", item)
            # Check for "Name(Qty)" format (current but with space)
            current_match = re.match(r"^(.+)\((\d+)\)$", item)
            
            if legacy_match:
                qty = legacy_match.group(1)
                name = legacy_match.group(2)
                new_items.append(f"{name}({qty})")
                modified = True
            elif current_match:
                # Standardize to Name(Qty) - mostly just ensures no extra spaces
                name = current_match.group(1).strip()
                qty = current_match.group(2)
                new_items.append(f"{name}({qty})")
                # If there was a space in the original string, it's still "modified" conceptually
                # but split/join will naturally fix it.
            else:
                new_items.append(item)
        
        new_particulars = ",".join(new_items)
        if new_particulars != old_particulars:
            print(f"  -> Updating to: {new_particulars}")
            await conn.execute("UPDATE loan_data SET particulars = $1 WHERE loan_number = $2", new_particulars, loan_number)
        else:
            print("  -> No change needed.")
            
    await conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(migrate_particulars())
