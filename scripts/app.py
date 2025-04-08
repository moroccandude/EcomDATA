import os
import json
import random
import pandas as pd
from faker import Faker
from datetime import datetime

fake = Faker()
staging_folder = "./Staging"
os.makedirs(staging_folder, exist_ok=True)

def generate_orders(num_orders=100):
    orders = [{"order_id": fake.uuid4(), "customer_id": fake.uuid4(),
               "order_date": fake.date_this_year().isoformat(),
               "status": random.choice(["CREATED", "SHIPPED", "DELIVERED", "CANCELLED"]),
               "product_id": fake.uuid4(), "quantity": random.randint(1, 5),
               "price": round(random.uniform(10, 500), 2)} for _ in range(num_orders)]
    df = pd.DataFrame(orders)
    df.to_csv(os.path.join(staging_folder, f"orders_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"), index=False)

def generate_logs(num_logs=200):
    logs = [{"event_id": fake.uuid4(), "user_id": fake.uuid4(), "event_type": random.choice(["click", "view", "purchase"]),
             "timestamp": datetime.now().isoformat()} for _ in range(num_logs)]
    with open(os.path.join(staging_folder, f"logs_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"), "w") as f:
        json.dump(logs, f, indent=4)

if __name__=='__main__' :
    # Generate sample data
    generate_orders()
    generate_logs()


