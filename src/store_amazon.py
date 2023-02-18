#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
import traceback

from amazon.paapi import AmazonAPI
from paapi5_python_sdk.get_items_resource import GetItemsResource
from paapi5_python_sdk.condition import Condition

PAAPI_SPLIT = 10


def fetch_price(config, asin_list):
    if len(asin_list) == 0:
        return {}

    logging.info(
        "PAAPI GetItems: ASIN = [ {asin_list} ]".format(asin_list=", ".join(asin_list))
    )

    amazon_api = AmazonAPI(
        config["amazon"]["access_key"],
        config["amazon"]["secret_key"],
        config["amazon"]["associate"],
        "JP",
    )

    price_map = {}
    for i, asin_sub_list in enumerate(
        [asin_list[i : i + PAAPI_SPLIT] for i in range(0, len(asin_list), PAAPI_SPLIT)]
    ):
        if i != 0:
            time.sleep(10)

        resp = amazon_api.get_items(
            asin_sub_list,
            condition=Condition.NEW,
            get_items_resource=[
                GetItemsResource.OFFERS_SUMMARIES_LOWESTPRICE,
                GetItemsResource.ITEMINFO_CLASSIFICATIONS,
                GetItemsResource.IMAGES_PRIMARY_MEDIUM,
                GetItemsResource.IMAGES_PRIMARY_SMALL,
            ],
        )

        for asin, product in resp["data"].items():
            product_info = product.to_dict()
            if product_info["offers"] is None:
                continue

            item = {}
            for offer in product_info["offers"]["summaries"]:
                if offer["condition"]["value"] != "New":
                    continue
                item["price"] = int(offer["lowest_price"]["amount"])
                break

            if "price" not in item:
                continue

            item["thumb_url"] = product_info["images"]["primary"]["medium"]["url"]

            price_map[asin] = item

    return price_map


def check_list(config, item_list):
    try:
        price_map = fetch_price(config, list(map(lambda item: item["asin"], item_list)))
        for item in item_list:
            if item["asin"] in price_map:
                item["stock"] = 1
                item["price"] = price_map[item["asin"]]["price"]
                item["thumb_url"] = price_map[item["asin"]]["thumb_url"]
            else:
                item["stock"] = 0
        return item_list
    except:
        logging.error(traceback.format_exc())
        return []


if __name__ == "__main__":
    import pprint
    from config import load_config

    config = load_config()

    pprint.pprint(
        fetch_price(
            config,
            ["B0BPBXPCT5", "B00C7FG7YO", "B09M6GW286", "B092HFNCDR", "B09T9YVP3B"],
        )
    )
