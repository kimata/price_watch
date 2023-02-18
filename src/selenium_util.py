#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
import inspect
import pathlib
import os
import shutil

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.core.utils import ChromeType
from webdriver_manager.chrome import ChromeDriverManager

DATA_PATH = pathlib.Path(os.path.dirname(__file__)).parent / "data"


def create_driver_impl(profile_name, data_path):
    chrome_data_path = data_path / "chrome"
    log_path = data_path / "log"

    os.makedirs(chrome_data_path, exist_ok=True)
    os.makedirs(log_path, exist_ok=True)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")  # for Docker
    options.add_argument("--disable-dev-shm-usage")  # for Docker

    options.add_argument("--lang=ja-JP")
    options.add_argument("--window-size=1920,1080")

    options.add_argument(
        '--user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0"'
    )
    options.add_argument("--user-data-dir=" + str(chrome_data_path / profile_name))

    # NOTE: 下記がないと，snap で入れた chromium が「LC_ALL: cannot change locale (ja_JP.UTF-8)」
    # と出力し，その結果 ChromeDriverManager がバージョンを正しく取得できなくなる
    os.environ["LC_ALL"] = "C"

    if shutil.which("google-chrome") is not None:
        chrome_type = ChromeType.GOOGLE
    else:
        chrome_type = ChromeType.CHROMIUM

    driver = webdriver.Chrome(
        service=Service(
            ChromeDriverManager(chrome_type=chrome_type).install(),
            log_path=str(log_path / "webdriver.log"),
            service_args=["--verbose"],
        ),
        options=options,
    )

    return driver


def create_driver(profile_name="Default", data_path=DATA_PATH):
    # NOTE: 1回だけ自動リトライ
    try:
        return create_driver_impl(profile_name, data_path)
    except:
        return create_driver_impl(profile_name, data_path)


def xpath_exists(driver, xpath):
    return len(driver.find_elements(By.XPATH, xpath)) != 0


def click_xpath(driver, xpath, wait=None, move=False, is_warn=True):
    if wait is not None:
        wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        time.sleep(0.5)

    if xpath_exists(driver, xpath):
        elem = driver.find_element(By.XPATH, xpath)
        action = ActionChains(driver)
        action.move_to_element(elem)
        action.perform()

        elem.click()
        return True
    else:
        if is_warn:
            logging.warning("Element is not found: {xpath}".format(xpath=xpath))
        return False


def is_display(driver, xpath):
    return (len(driver.find_elements(By.XPATH, xpath)) != 0) and (
        driver.find_element(By.XPATH, xpath).is_displayed()
    )


def dump_page(driver, dump_path, index):
    name = inspect.stack()[1].function.replace("<", "").replace(">", "")
    dump_path = pathlib.Path(dump_path)

    os.makedirs(str(dump_path), exist_ok=True)

    png_path = dump_path / (
        "{name}_{index:02d}.{ext}".format(name=name, index=index, ext="png")
    )
    htm_path = dump_path / (
        "{name}_{index:02d}.{ext}".format(name=name, index=index, ext="htm")
    )

    driver.save_screenshot(str(png_path))

    with open(str(htm_path), "w") as f:
        f.write(driver.page_source)

    logging.info("page dump: {index:02d}.".format(index=index))
