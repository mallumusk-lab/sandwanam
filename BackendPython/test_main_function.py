from main import noOfDaysCalculation
from datetime import datetime

print(f"Same day: {noOfDaysCalculation('2026-03-16', '2026-03-16')}")
print(f"ISO same day: {noOfDaysCalculation('2026-03-16', '2026-03-16T22:53:43')}")
