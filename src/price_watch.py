#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import logging.handlers

import time
import os
import sys
import random
import re
import urllib

import pathlib
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium_util import create_driver, dump_page

import logger
import history
import captcha
import notify_slack
from config import load_config

CONFIG_TARGET_PATH = "../target.yml"

DATA_PATH = pathlib.Path(os.path.dirname(__file__)).parent / "data"
DUMP_PATH = str(DATA_PATH / "debug")

TIMEOUT_SEC = 4
SLEEP_UNIT = 60
CHECK_INTERVAL_SEC = 5


def sleep_until(end_time):
    sleep_remain = end_time - time.time()
    logging.info("sleep {sleep:,} sec...".format(sleep=int(sleep_remain)))

    while True:
        # NOTE: Livenss がタイムアウトしないよう，定期的に更新する
        pathlib.Path(config["liveness"]["file"]).touch()

        sleep_remain = end_time - time.time()
        if sleep_remain < 0:
            return
        elif sleep_remain < SLEEP_UNIT:
            time.sleep(sleep_remain)
        else:
            time.sleep(SLEEP_UNIT)


def exec_action(config, driver, wait, action_list):
    for action in action_list:
        logging.debug("action: {action}.".format(action=action["type"]))
        if action["type"] == "input":
            if len(driver.find_elements(By.XPATH, action["xpath"])) == 0:
                logging.debug("Element not found. Interrupted.")
                return
            driver.find_element(By.XPATH, action["xpath"]).send_keys(action["value"])
            time.sleep(2)
        elif action["type"] == "click":
            if len(driver.find_elements(By.XPATH, action["xpath"])) == 0:
                logging.debug("Element not found. Interrupted.")
                return
            driver.find_element(By.XPATH, action["xpath"]).click()
            time.sleep(5)
        elif action["type"] == "recaptcha":
            captcha.resolve_mp3(config, driver, wait)
            time.sleep(2)
        elif action["type"] == "captcha":
            input_xpath = '//input[@id="captchacharacters"]'
            if len(driver.find_elements(By.XPATH, input_xpath)) == 0:
                logging.debug("Element not found. Interrupted.")
                return
            domain = urllib.parse.urlparse(driver.current_url).netloc

            logging.warning(
                "Resolve captche is needed at {domain}.".format(domain=domain)
            )

            dump_page(driver, DUMP_PATH, int(random.random() * 100))
            code = input("{domain} captcha: ".format(domain=domain))

            driver.find_element(By.XPATH, input_xpath).send_keys(code)
            driver.find_element(By.XPATH, '//button[@type="submit"]').click()
        elif action["type"] == "sixdigit":
            # NOTE: これは今のところ Ubiquiti Store USA 専用
            digit_code = input(
                "{domain} app code: ".format(
                    domain=urllib.parse.urlparse(driver.current_url).netloc
                )
            )
            for i, code in enumerate(list(digit_code)):
                driver.find_element(
                    By.XPATH, '//input[@data-id="' + str(i) + '"]'
                ).send_keys(code)
            time.sleep(2)


def process_data(config, item, last):
    if (
        (last is None)
        or ((item["stock"] == 1) and (item["price"] != last["price"]))
        or (item["stock"] != last["stock"])
    ):
        # NOTE: 下記いずれかの場合，履歴を記録する．
        # - 履歴データが無い場合
        # - 在庫がある状態で価格が変化した
        # - 在庫状況が変化した
        # (在庫が無い状態で価格が変化した場合は記録しない)

        if (last is not None) and (item["stock"] == 0):
            # NOTE: 在庫がなくなった場合，価格は前回のものを採用する．
            # (在庫がなくなった瞬間に更新された価格は記録しない)
            item["price"] = last["price"]

        history.insert(item)

    if last is None:
        logging.warning(
            "{name}: watch start {new_price:,}{price_unit}. ({stock})".format(
                name=item["name"],
                new_price=item["price"],
                price_unit=item["price_unit"],
                stock="out of stock" if item["stock"] == 0 else "in stock",
            )
        )
    else:
        item["old_price"] = last["price"]

        if item["stock"] == 1:
            if item["price"] < last["price"]:
                logging.warning(
                    "{name}: price updated {old_price:,}{price_unit} ➡ {new_price:,}{price_unit}.".format(
                        name=item["name"],
                        old_price=last["price"],
                        new_price=item["price"],
                        price_unit=item["price_unit"],
                    )
                )
                notify_slack.send(config, item)
            elif last["stock"] == 0:
                logging.warning(
                    "{name}: back in stock {new_price:,}{price_unit}.".format(
                        name=item["name"],
                        new_price=item["price"],
                        price_unit=item["price_unit"],
                    )
                )
                notify_slack.send(config, item)
            else:
                logging.info(
                    "{name}: {new_price:,}{price_unit} ({stock}).".format(
                        name=item["name"],
                        new_price=item["price"],
                        price_unit=item["price_unit"],
                        stock="out of stock" if item["stock"] == 0 else "in stock",
                    )
                )
        else:
            logging.info(
                "{name}: {new_price:,}{price_unit} ({stock}).".format(
                    name=item["name"],
                    new_price=item["price"],
                    price_unit=item["price_unit"],
                    stock="out of stock" if item["stock"] == 0 else "in stock",
                )
            )

    return True


def check_item(config, driver, item):
    wait = WebDriverWait(driver, TIMEOUT_SEC)

    if "preload" in item:
        driver.get(item["preload"]["url"])
        time.sleep(2)
        exec_action(config, driver, wait, item["preload"]["action"])

    driver.get(item["url"])
    time.sleep(2)

    if "action" in item:
        exec_action(config, driver, wait, item["action"])

    if len(driver.find_elements(By.XPATH, item["price_xpath"])) == 0:
        logging.warning("{name}: price not found.".format(name=item["name"]))
        dump_page(driver, DUMP_PATH, int(random.random() * 100))
        return False

    price_text = driver.find_element(By.XPATH, item["price_xpath"]).text

    m = re.match(r".*?(\d{1,3}(?:,\d{3})*)", price_text)
    item["price"] = int(m.group(1).replace(",", ""))

    if "unavailable_xpath" in item:
        if len(driver.find_elements(By.XPATH, item["unavailable_xpath"])) != 0:
            item["stock"] = 0
        else:
            item["stock"] = 1
    else:
        item["stock"] = 1

    return process_data(config, item, history.last(item["name"], item["store"]))


def do_work(config, driver, item_list):
    for item in item_list:
        try:
            check_item(config, driver, item.copy())
            pathlib.Path(config["liveness"]["file"]).touch()
        except:
            logging.error("URL: {url}".format(url=driver.current_url))
            logging.error(traceback.format_exc())
            dump_page(driver, DUMP_PATH, int(random.random() * 100))
            logging.warning("Exit.")
            pass
        time.sleep(CHECK_INTERVAL_SEC)


def load_item_list():
    item_list = []
    target_config = load_config(CONFIG_TARGET_PATH)

    store_map = {}
    for store in target_config["store_list"]:
        store_map[store["name"]] = store

    for item in target_config["item_list"]:
        merged_item = dict(store_map[item["store"]], **item)

        if "price_unit" not in merged_item:
            merged_item["price_unit"] = "円"

        item_list.append(merged_item)

    return item_list


os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

logger.init("bot.price_watch")

logging.info("Start.")

config = load_config()
driver = create_driver()

while True:
    start_time = time.time()

    do_work(config, driver, load_item_list())

    sleep_until(start_time + config["interval"])
