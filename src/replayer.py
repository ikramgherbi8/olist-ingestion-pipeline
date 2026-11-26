# tools for reading CSVs, handling folders, copying files and waiting
import argparse
import csv
import os
import shutil
import time
from collections import defaultdict

# where the original files are and where the pieces will be dropped
SRC = "data/archive"
OUT = "data/landing"

# small lookup files, dropped once at the start
REFERENCE_FILES = [
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
]


# read a CSV from data/archive, return the column names and all rows
def read_csv(name):
    path = os.path.join(SRC, name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


# write rows to a CSV file, with the header line first
def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# group rows by one column, e.g. all items of the same order_id
def group_by(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return groups


def main():
    # options typed after the command: first day, last day, seconds between days
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="0000-01-01")
    parser.add_argument("--end", default="9999-12-31")
    parser.add_argument("--delay", type=float, default=5)
    args = parser.parse_args()

    # make sure the landing folder exists
    os.makedirs(OUT, exist_ok=True)

    # copy the reference files once, into a temporary folder first,
    # then rename it so it appears all at once
    ref_final = os.path.join(OUT, "reference")
    if not os.path.exists(ref_final):
        ref_tmp = ref_final + ".tmp"
        shutil.rmtree(ref_tmp, ignore_errors=True)
        os.makedirs(ref_tmp)
        for name in REFERENCE_FILES:
            shutil.copy(os.path.join(SRC, name), os.path.join(ref_tmp, name))
        os.rename(ref_tmp, ref_final)
        print("reference files dropped")

    # load the four event files into memory
    order_fields, orders = read_csv("olist_orders_dataset.csv")
    item_fields, items = read_csv("olist_order_items_dataset.csv")
    pay_fields, payments = read_csv("olist_order_payments_dataset.csv")
    rev_fields, reviews = read_csv("olist_order_reviews_dataset.csv")

    # lookups: items and payments by order_id, so we don't search the whole file each time
    items_by_order = group_by(items, "order_id")
    payments_by_order = group_by(payments, "order_id")

    # orders grouped by purchase day (first 10 characters of the date: yyyy-mm-dd)
    orders_by_day = defaultdict(list)
    for row in orders:
        orders_by_day[row["order_purchase_timestamp"][:10]].append(row)

    # reviews grouped by the day they were created
    reviews_by_day = defaultdict(list)
    for row in reviews:
        reviews_by_day[row["review_creation_date"][:10]].append(row)

    # all days that have orders or reviews, in date order, limited to --start / --end
    days = sorted(set(orders_by_day) | set(reviews_by_day))
    days = [d for d in days if args.start <= d <= args.end]

    # one loop turn = one day
    for day in days:
        # if this day was already dropped, skip it (lets you stop and restart)
        final = os.path.join(OUT, day)
        if os.path.exists(final):
            print(day, "already there, skipped")
            continue

        # pick the rows of this day: orders, then their items and payments, then reviews
        day_orders = orders_by_day.get(day, [])
        day_items = [r for o in day_orders for r in items_by_order.get(o["order_id"], [])]
        day_pays = [r for o in day_orders for r in payments_by_order.get(o["order_id"], [])]
        day_reviews = reviews_by_day.get(day, [])

        # write the four files into a temporary folder, then rename it,
        # so a half-written day is never visible
        tmp = final + ".tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        write_csv(os.path.join(tmp, "orders.csv"), order_fields, day_orders)
        write_csv(os.path.join(tmp, "order_items.csv"), item_fields, day_items)
        write_csv(os.path.join(tmp, "order_payments.csv"), pay_fields, day_pays)
        write_csv(os.path.join(tmp, "order_reviews.csv"), rev_fields, day_reviews)
        os.rename(tmp, final)

        # show the day and the number of orders, items, payments, reviews
        print(day, len(day_orders), len(day_items), len(day_pays), len(day_reviews))

        # wait before the next day, to act like a live source
        time.sleep(args.delay)


# start the script
main()