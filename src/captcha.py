#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import tempfile
import urllib
import os

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from speech_recognition import Recognizer, AudioFile
import pydub

from selenium_util import click_xpath


def recog_audio(audio_url):
    mp3_file = tempfile.NamedTemporaryFile(mode="wb", delete=False)
    wav_file = tempfile.NamedTemporaryFile(mode="wb", delete=False)

    try:
        urllib.request.urlretrieve(audio_url, mp3_file.name)

        pydub.AudioSegment.from_mp3(mp3_file.name).export(wav_file.name, format="wav")

        recognizer = Recognizer()
        recaptcha_audio = AudioFile(wav_file.name)
        with recaptcha_audio as source:
            audio = recognizer.record(source)

        return recognizer.recognize_google(audio, language="en-US")
    except:
        raise
    finally:
        os.unlink(mp3_file.name)
        os.unlink(wav_file.name)


def resolve_mp3(config, driver, wait):
    wait.until(
        EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, '//iframe[@title="reCAPTCHA"]')
        )
    )
    click_xpath(
        driver,
        '//span[contains(@class, "recaptcha-checkbox")]',
        move=True,
    )
    driver.switch_to.default_content()
    wait.until(
        EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, '//iframe[contains(@title, "reCAPTCHA による確認")]')
        )
    )
    wait.until(
        EC.element_to_be_clickable((By.XPATH, '//div[@id="rc-imageselect-target"]'))
    )
    click_xpath(driver, '//button[contains(@title, "確認用の文字を音声")]', move=True)
    time.sleep(0.5)

    audio_url = driver.find_element(
        By.XPATH, '//audio[@id="audio-source"]'
    ).get_attribute("src")

    text = recog_audio(audio_url)

    input_elem = driver.find_element(By.XPATH, '//input[@id="audio-response"]')
    input_elem.send_keys(text.lower())
    input_elem.send_keys(Keys.ENTER)

    driver.switch_to.default_content()
