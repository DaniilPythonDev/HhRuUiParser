"""
TODO: Парсер донных с сайта hh.ru c ui интерфейсом
"""

import asyncio
import csv
import datetime
import fnmatch
import json
import sys
import time
from dataclasses import dataclass

import aiohttp
import requests
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QThread
from bs4 import BeautifulSoup as Soup4
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class ScrapingData:
    protsessbar = 0
    count = 0
    count_done = 0
    main_link = 'https://hh.ru'
    links = {'site_link': f'{main_link}/search/vacancy',
             'search_area_link': f'{main_link}/area_switcher/search',
             'authorization_link': f'{main_link}/account/login?backurl=%2F&hhtmFrom=main',
             'contact_link': f'{main_link}/vacancy/'}
    params = {'text': '',
              'items_on_page': '20',
              'search_field': '',
              'area': '',
              'search_period': '',
              'page': 0}
    params_search_area = {'q': '', 'lang': 'RU'}
    headers = {'user-agent': UserAgent().chrome,
               'sec-ch-ua-platform': "Windows"}
    cookies = {}
    file_name_cooke = f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}_cookies.json'
    file_name_csv = f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}_{params.get("text")}'
    file_name_log = 'log.txt'
    file_name_default = 'default_data.json'
    login = {'email': '',
             'password': ''}


class WriteReadFile:

    def __init__(self, name_file: str = None, kirilic: bool = True):
        self.name_file = name_file
        if kirilic:
            self.encoding = 'cp1251'
        else:
            self.encoding = 'utf-8'

    def write(self, write_data, newline=None, delimiter=None, _mod='w'):
        try:
            with open(file=self.name_file, mode=_mod, encoding=self.encoding, newline=newline) as fle:
                if fnmatch.fnmatch(self.name_file, '*.json'):
                    json.dump(write_data, fle)
                elif fnmatch.fnmatch(self.name_file, '*.csv'):
                    csv_writer = csv.writer(fle, delimiter=delimiter)
                    csv_writer.writerows(write_data)
                else:
                    fle.write(write_data)
        except Exception as _es:
            print(f'Ошибка при записи данных в файл: {_es}')
        else:
            return self.name_file

    def read(self):
        try:
            with open(file=self.name_file, mode='r', encoding=self.encoding) as fle:
                if fnmatch.fnmatch(self.name_file, '*.json'):
                    return json.load(fle)
                else:
                    return fle.read()
        except json.JSONDecodeError:
            return {}
        except Exception as _es:
            print(f'Ошибка при чтении данных из файла: {_es}')

    def append(self, append_data, newline=None, delimiter=None):
        return WriteReadFile(name_file=self.name_file).write(write_data=append_data, newline=newline,
                                                             delimiter=delimiter, _mod='a')


class Authorization:

    @staticmethod
    def authorization_selenium():
        driver = None
        try:
            options = webdriver.ChromeOptions()
            options.add_argument(f'user-agent={ScrapingData.headers.get("user-agent")}')

            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
            driver.get(url=ScrapingData.links.get('authorization_link'))

            time.sleep(0.3)

            passw_email_butt = driver.find_element(by=By.CSS_SELECTOR,
                                                   value='[data-qa="expand-login-by-password"]')
            passw_email_butt.click()

            time.sleep(0.3)

            email_input = driver.find_element(by=By.CSS_SELECTOR, value='[data-qa="login-input-username"]')
            email_input.clear()
            email_input.send_keys(ScrapingData.login.get('email'))

            time.sleep(0.3)

            password_input = driver.find_element(by=By.CSS_SELECTOR, value='[data-qa="login-input-password"]')
            password_input.clear()
            password_input.send_keys(ScrapingData.login.get('password'))

            time.sleep(0.3)

            submit_butt = driver.find_element(by=By.CSS_SELECTOR, value='[data-qa="account-login-submit"]')
            submit_butt.click()
            time.sleep(20)
            submit_butt.click()

            time.sleep(4)
            for e in driver.get_cookies():
                ScrapingData.cookies[e['name']] = e['value']

        except Exception as ex:
            print(f'Ошибка при авторизации: {ex}')
        finally:
            driver.close()
            driver.quit()
            return ScrapingData.cookies


class ScrapingAsync:

    @staticmethod
    async def async_session(get_area=False, pages_data=True, ui=None):
        async with aiohttp.ClientSession(headers=ScrapingData.headers, cookies=ScrapingData.cookies or None) as session:
            if get_area:
                return await ScrapingAsync.async_get_area_id(session=session)
            elif pages_data:
                async with session.get(url=ScrapingData.links.get('site_link'),
                                       params=ScrapingData.params) as response:
                    html_text = await response.text()
                    soup = Soup4(html_text, 'lxml')
                    main_block = soup.find(class_='vacancy-serp-content')
                    pager_blok = main_block.find(class_='pager')

                    if pager_blok:
                        ScrapingData.count += int(pager_blok.find_all(class_='bloko-button')[-2].text.strip())

                    tasks = []
                    for page in range(ScrapingData.count):
                        task = asyncio.create_task(ScrapingAsync.async_page_data(session=session, num=page, ui=ui))
                        tasks.append(task)
                    data = await asyncio.gather(*tasks)
                    return data

    @staticmethod
    async def async_get_area_id(session):
        async with session.get(url=ScrapingData.links.get('search_area_link'),
                               params=ScrapingData.params_search_area) as response:
            json_data = await response.json()
            return dict(json_data)

    @staticmethod
    async def async_page_data(session, num, ui=None):
        ScrapingData.params['page'] = num
        async with session.get(url=ScrapingData.links.get('site_link'),
                               params=ScrapingData.params) as response:
            html = await response.text()
            soup = Soup4(html, 'lxml')

            all_data = []
            main_block = soup.find(class_='vacancy-serp-content')
            data_blocks = main_block.find_all(class_='serp-item')
            for d in data_blocks:
                data_vacansi = []
                tag_a = d.find('a', {'class': 'serp-item__title'})
                name_vacanse = tag_a.text
                href = tag_a.get('href')
                name_company = d.find('div', {'class': 'vacancy-serp-item__meta-info-company'}).text.strip()
                area = d.find('div', {'data-qa': 'vacancy-serp__vacancy-address'}).text
                data_vacansi += [name_company, name_vacanse, href, area]
                button_check = d.find(class_='vacancy-serp-actions').find('button').text.strip()
                if str(button_check).startswith('Показать контакты'):
                    async with session.get(url=f"{ScrapingData.links.get('contact_link')}"
                                               f"{href.split('?')[0].split('/')[-1]}/contacts") as response_cont:
                        try:
                            contacts_json_data = dict(await response_cont.json())
                        except Exception as _:
                            contacts_json_data = dict()
                        # print(response_cont.status, contacts_json_data)
                        if contacts_json_data:
                            fio = contacts_json_data.get('fio', 'NONE')
                            email = contacts_json_data.get('email', 'NONE')
                            if dict(contacts_json_data.get('phones')):
                                phones = dict(contacts_json_data.get('phones')).get('phones')[0]
                                tel = f"+{phones.get('country')} {phones.get('city')} {phones.get('number')}"
                                comment = f"{phones.get('comment', 'Нет коментарий!')}"
                            else:
                                tel = comment = 'Нет данных!'
                        else:
                            fio = email = tel = comment = 'Нет данных!'
                else:
                    fio = email = tel = comment = 'Нет данных!'
                data_vacansi += [fio, email, tel, comment]
                # print(data_vacansi)
                all_data.append(tuple(data_vacansi))
            ScrapingData.count_done += 1
            ScrapingData.protsessbar = int(round(100 / ScrapingData.count) * ScrapingData.count_done)
            ui.progressBar.setProperty("value", ScrapingData.protsessbar)
            return all_data


class ScrapingSync:

    @staticmethod
    def request_data(url, cookies=None, url_data=None, session=False, metod: str = 'get' or 'post',
                     bs4=False, get_json=False):
        try:
            info = None
            if not session:
                info = requests.get(url=url, headers=ScrapingData.headers, cookies=cookies, data=url_data)
            else:
                sess = requests.Session()
                if metod == 'get':
                    info = sess.get(url=url, headers=ScrapingData.headers, cookies=cookies, data=url_data)
            if bs4:
                soup4 = Soup4(info.text, 'lxml')
                return soup4
            if get_json:
                try:
                    # print(info.status_code)
                    return info.json()
                except Exception as _ex:
                    print(_ex)
                    return dict()
            return info.text
        except Exception:
            time.sleep(30)
            return ScrapingSync().request_data(url=url, cookies=cookies, url_data=url_data, metod='get', bs4=True)

    @staticmethod
    def get_data(get_count=False, check=False):
        all_data = []
        soup = ScrapingSync().request_data(url=ScrapingData.links.get('site_link'), cookies=ScrapingData.cookies,
                                           url_data=ScrapingData.params, metod='get', bs4=True)
        main_block = soup.find(class_='vacancy-serp-content')
        if check:
            check_auth = soup.find('div', {"class": "supernova-navi-underline"})
            if not check_auth:
                return False
            else:
                return True
        elif get_count:
            pager_blok = main_block.find(class_='pager')
            if pager_blok:
                count = pager_blok.find_all(class_='bloko-button')[-2].text.strip()
                return int(count)
            else:
                return 0
        else:
            data_blocks = main_block.find_all(class_='serp-item')
            for d in data_blocks:
                data_vacansi = []
                tag_a = d.find('a', {'class': 'serp-item__title'})
                name_vacanse = tag_a.text
                href = tag_a.get('href')
                name_company = d.find('div', {'class': 'vacancy-serp-item__meta-info-company'}).text.strip()
                area = d.find('div', {'data-qa': 'vacancy-serp__vacancy-address'}).text
                button_check = d.find(class_='vacancy-serp-actions').find('button').text.strip()
                data_vacansi += [name_company, name_vacanse, href, area]
                if str(button_check).startswith('Показать контакты'):
                    contacts_json_data = ScrapingSync().request_data(url=f"{href.split('?')[0]}/contacts",
                                                                     cookies=ScrapingData.cookies, get_json=True)
                    # print(contacts_json_data)
                    if contacts_json_data:
                        fio = contacts_json_data.get('fio')
                        email = contacts_json_data.get('email')
                        if contacts_json_data.get('phones'):
                            phones = dict(contacts_json_data.get('phones')).get('phones')[0]
                            tel = f"+{phones.get('country')} {phones.get('city')} {phones.get('number')}"
                            comment = f"{phones.get('comment', 'Нет коментарий!')}"
                        else:
                            fio = email = tel = comment = 'Нет данных!'
                        data_vacansi += [fio, email, tel, comment]
                    else:
                        fio = email = tel = comment = 'Нет данных!'
                        data_vacansi += [fio, email, tel, comment]
                else:
                    fio = email = tel = comment = 'Нет данных!'
                    data_vacansi += [fio, email, tel, comment]
                all_data.append(tuple(data_vacansi))
            return all_data


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(500, 800)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        font = QtGui.QFont()
        font.setPointSize(15)
        font.setItalic(False)
        font.setUnderline(False)
        self.centralwidget.setFont(font)
        self.centralwidget.setStyleSheet("QWidget{\n"
                                         "    background-color: rgb(50, 50, 50);\n"
                                         "}\n"
                                         "QLineEdit, QPushButton, QComboBox{\n"
                                         "    border-right: 1px solid  #ff0;\n"
                                         "    border-bottom: 1px solid #ff0;\n"
                                         "    background-color: rgb(100, 100, 100);\n"
                                         "    border-radius: 5px;\n"
                                         "    font-size: 15px;\n"
                                         "    color: rgb(255, 255, 255);\n"
                                         "}\n"
                                         "QPushButton:hover{\n"
                                         "    color: rgb(255, 255, 0);\n"
                                         "}\n"
                                         "QPushButton:pressed{\n"
                                         "    color: rgb(0, 0, 255);\n"
                                         "    border: 0;\n"
                                         "}\n"
                                         "QLineEdit:selected, QPushButton:selected, QComboBox:selected{\n"
                                         "    border-right: 1px solid  #f00;\n"
                                         "    border-bottom: 1px solid #f00;\n"
                                         "}")
        self.centralwidget.setObjectName("centralwidget")
        self.frame = QtWidgets.QFrame(self.centralwidget)
        self.frame.setGeometry(QtCore.QRect(0, 0, 500, 800))
        self.frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.frame.setObjectName("frame")
        self.login_input = QtWidgets.QLineEdit(self.frame)
        self.login_input.setGeometry(QtCore.QRect(10, 210, 480, 30))
        font = QtGui.QFont()
        font.setPointSize(-1)
        self.login_input.setFont(font)
        self.login_input.setStyleSheet("")
        self.login_input.setText("")
        self.login_input.setObjectName("login_input")
        self.logo = QtWidgets.QLabel(self.frame)
        self.logo.setEnabled(True)
        self.logo.setGeometry(QtCore.QRect(200, 40, 100, 100))
        font = QtGui.QFont()
        font.setPointSize(45)
        font.setBold(False)
        font.setItalic(False)
        font.setWeight(50)
        font.setStrikeOut(False)
        font.setKerning(True)
        self.logo.setFont(font)
        self.logo.setMouseTracking(True)
        self.logo.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.logo.setAutoFillBackground(False)
        self.logo.setStyleSheet("background-color: rgb(255, 11, 3);\n"
                                "color: rgb(255, 255, 255);\n"
                                "border-radius: 50%;\n"
                                "")
        self.logo.setTextFormat(QtCore.Qt.TextFormat.AutoText)
        self.logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.logo.setWordWrap(False)
        self.logo.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.logo.setObjectName("logo")
        self.password_input = QtWidgets.QLineEdit(self.frame)
        self.password_input.setGeometry(QtCore.QRect(10, 290, 480, 30))
        self.password_input.setStyleSheet("")
        self.password_input.setInputMask("")
        self.password_input.setText("")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password_input.setObjectName("password_input")
        self.text_login = QtWidgets.QLabel(self.frame)
        self.text_login.setGeometry(QtCore.QRect(10, 180, 100, 25))
        self.text_login.setStyleSheet("color: rgb(255, 255, 255);\n"
                                      "font-size: 15px;")
        self.text_login.setObjectName("text_login")
        self.text_password = QtWidgets.QLabel(self.frame)
        self.text_password.setGeometry(QtCore.QRect(10, 260, 100, 25))
        self.text_password.setStyleSheet("color: rgb(255, 255, 255);\n"
                                         "font-size: 15px;")
        self.text_password.setObjectName("text_password")
        self.text_key_word = QtWidgets.QLabel(self.frame)
        self.text_key_word.setGeometry(QtCore.QRect(10, 340, 265, 18))
        self.text_key_word.setStyleSheet("color: rgb(255, 255, 255);\n"
                                         "font-size: 15px;")
        self.text_key_word.setObjectName("text_key_word")
        self.key_word_input = QtWidgets.QLineEdit(self.frame)
        self.key_word_input.setGeometry(QtCore.QRect(10, 370, 480, 30))
        font = QtGui.QFont()
        font.setPointSize(-1)
        self.key_word_input.setFont(font)
        self.key_word_input.setStyleSheet("")
        self.key_word_input.setText("")
        self.key_word_input.setObjectName("key_word_input")
        self.text_area = QtWidgets.QLabel(self.frame)
        self.text_area.setGeometry(QtCore.QRect(10, 420, 150, 25))
        self.text_area.setStyleSheet("color: rgb(255, 255, 255);\n"
                                     "font-size: 15px;")
        self.text_area.setObjectName("text_area")
        self.area_input = QtWidgets.QLineEdit(self.frame)
        self.area_input.setGeometry(QtCore.QRect(10, 450, 480, 30))
        font = QtGui.QFont()
        font.setPointSize(-1)
        self.area_input.setFont(font)
        self.area_input.setStyleSheet("")
        self.area_input.setText("")
        self.area_input.setObjectName("area_input")
        self.text_search_by = QtWidgets.QLabel(self.frame)
        self.text_search_by.setGeometry(QtCore.QRect(10, 500, 150, 25))
        self.text_search_by.setStyleSheet("color: rgb(255, 255, 255);\n"
                                          "font-size: 15px;")
        self.text_search_by.setObjectName("text_search_by")
        self.search_by_v = QtWidgets.QComboBox(self.frame)
        self.search_by_v.setGeometry(QtCore.QRect(10, 530, 200, 30))
        font = QtGui.QFont()
        font.setPointSize(-1)
        self.search_by_v.setFont(font)
        self.search_by_v.setStyleSheet("")
        self.search_by_v.setObjectName("search_by_v")
        self.search_by_v.addItem("")
        self.search_by_v.addItem("")
        self.search_by_v.addItem("")
        self.text_search_time = QtWidgets.QLabel(self.frame)
        self.text_search_time.setGeometry(QtCore.QRect(290, 500, 150, 25))
        self.text_search_time.setStyleSheet("color: rgb(255, 255, 255);\n"
                                            "font-size: 15px;")
        self.text_search_time.setObjectName("text_search_time")
        self.search_time_v = QtWidgets.QComboBox(self.frame)
        self.search_time_v.setGeometry(QtCore.QRect(290, 530, 200, 30))
        font = QtGui.QFont()
        font.setPointSize(-1)
        self.search_time_v.setFont(font)
        self.search_time_v.setStyleSheet("")
        self.search_time_v.setObjectName("search_time_v")
        self.search_time_v.addItem("")
        self.search_time_v.addItem("")
        self.search_time_v.addItem("")
        self.search_time_v.addItem("")
        self.search_time_v.addItem("")
        self.button_start = QtWidgets.QPushButton(self.frame)
        self.button_start.setGeometry(QtCore.QRect(10, 600, 150, 50))
        self.button_start.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.button_start.setStyleSheet("")
        self.button_start.setCheckable(False)
        self.button_start.setAutoDefault(False)
        self.button_start.setObjectName("button_start")
        self.progressBar = QtWidgets.QProgressBar(self.frame)
        self.progressBar.setGeometry(QtCore.QRect(10, 770, 480, 10))
        self.progressBar.setProperty("value", 0)
        self.progressBar.setTextVisible(False)
        self.progressBar.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.progressBar.setInvertedAppearance(False)
        self.progressBar.setObjectName("progressBar")
        self.checkBox = QtWidgets.QCheckBox(self.frame)
        self.checkBox.setGeometry(QtCore.QRect(10, 680, 300, 50))
        self.checkBox.setStyleSheet("background-color: rgb(100, 100, 100);\n"
                                    "border-radius: 5px;\n"
                                    "font-size: 15px;\n"
                                    "color: rgb(255, 255, 255);")
        self.checkBox.setIconSize(QtCore.QSize(25, 25))
        self.checkBox.setTristate(False)
        self.checkBox.setObjectName("checkBox")
        MainWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        self.handler()
        self.set_def_val()

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "HHPars"))
        self.logo.setText(_translate("MainWindow", "hh"))
        self.text_login.setText(_translate("MainWindow", "Логин:"))
        self.text_password.setText(_translate("MainWindow", "Пароль:"))
        self.text_key_word.setText(_translate("MainWindow", "Введите ключевое слово для поиска:"))
        self.text_area.setText(_translate("MainWindow", "Укажите город:"))
        self.text_search_by.setText(_translate("MainWindow", "Поиск по:"))
        self.search_by_v.setItemText(0, _translate("MainWindow", "названии вакансии"))
        self.search_by_v.setItemText(1, _translate("MainWindow", "названии компании"))
        self.search_by_v.setItemText(2, _translate("MainWindow", "описании вакансии"))
        self.text_search_time.setText(_translate("MainWindow", "Диапозон времени:"))
        self.search_time_v.setItemText(0, _translate("MainWindow", "За всё время"))
        self.search_time_v.setItemText(1, _translate("MainWindow", "За месяц"))
        self.search_time_v.setItemText(2, _translate("MainWindow", "За неделю"))
        self.search_time_v.setItemText(3, _translate("MainWindow", "За последние три дня"))
        self.search_time_v.setItemText(4, _translate("MainWindow", "За сутки"))
        self.button_start.setText(_translate("MainWindow", "Старт"))
        self.checkBox.setText(_translate("MainWindow", "Выполнить в ускоренным режиме"))

    def handler(self):
        self.button_start.clicked.connect(lambda: self.get_val())

    def set_def_val(self):
        def_data = WriteReadFile(name_file=ScrapingData.file_name_default).read()
        if def_data:
            self.login_input.setText(def_data.get('email'))
            self.password_input.setText(def_data.get('password'))
            self.key_word_input.setText(def_data.get('search_text'))
            self.area_input.setText(def_data.get('area'))
            self.search_by_v.setCurrentIndex(int(def_data.get('search_field')))
            self.search_time_v.setCurrentIndex(int(def_data.get('search_period')))

    async def data_validator(self, dict_data: dict):
        ScrapingData.login['email'] = dict_data.get('email')
        ScrapingData.login['password'] = dict_data.get('password')

        ScrapingData.params['text'] = dict_data.get('search_text')
        ScrapingData.params_search_area['q'] = dict_data.get("area", "")
        request_area = dict(await ScrapingAsync.async_session(get_area=True)).get('items')
        if len(request_area) == 1:
            request_area = dict(request_area[0])
            ScrapingData.params['area'] = request_area.get('areaId')

        elif 1 < len(request_area) == 0:
            self.text_area.setText(f"{self.text_area.text()} (Пожалуста введите точное название города!)")
            self.area_input.setStyleSheet("border-right: 1px solid  #f00;\n"
                                          "border-bottom: 1px solid #f00;\n")
            return False
        search_by_p = {'0': 'name', '1': 'company_name', '2': 'description'}
        ScrapingData.params['search_field'] = search_by_p.get(str(dict_data.get('search_field')))
        search_diapazon_time_p = {'0': '0', '4': '1', '3': '3', '2': '7', '1': '30'}
        ScrapingData.params['search_period'] = search_diapazon_time_p.get(str(dict_data.get('search_period')))
        return True

    async def start_script_pars(self, async_pars=True):
        Authorization.authorization_selenium()
        rez = list()
        if async_pars:
            rez = await ScrapingAsync.async_session(pages_data=True, ui=self)
        else:
            ScrapingData.count = ScrapingSync.get_data(get_count=True)
            full = 100 / ScrapingData.count
            for i in range(ScrapingData.count):
                ScrapingData.params['page'] = i
                rez.append(ScrapingSync.get_data())
                # print(int(full * i))
                self.progressBar.setProperty("value", int(full * (i + 1)))
        now_name_csv = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_data.csv"
        for data_list in rez:
            WriteReadFile(name_file=now_name_csv, kirilic=True).append(append_data=data_list, delimiter=';',
                                                                       newline='')

    def get_val(self):
        self.default_val = {'email': self.login_input, 'password': self.password_input,
                            'search_text': self.key_word_input, 'area': self.area_input,
                            'search_field': str(self.search_by_v.currentIndex()),
                            'search_period': str(self.search_time_v.currentIndex())}
        for k, fun in self.default_val.items():
            if k not in ('search_field', 'search_period'):
                if not fun.text():
                    fun.setStyleSheet("border-right: 1px solid  #f00;\n"
                                      "border-bottom: 1px solid #f00;\n")
                else:
                    self.default_val[k] = self.default_val.get(k).text()
                    fun.setStyleSheet("")
        is_val = [fun for fun in self.default_val.values() if type(fun) in (None, str, int)]
        if all(is_val) and len(is_val) == 6:
            WriteReadFile(name_file=ScrapingData.file_name_default).write(write_data=self.default_val)
            if self.checkBox.isChecked():
                self.start_process_pars = ProgressBar(mainWindow=self)
                self.start_process_pars.start()
            else:
                self.start_process_pars = ProgressBar(mainWindow=self, async_pars=False)
                self.start_process_pars.start()

    async def parser_start(self, dict_data, async_pars=True):
        is_valid = await self.data_validator(dict_data=dict_data)
        if is_valid:
            if async_pars:
                await self.start_script_pars()
            else:
                await self.start_script_pars(async_pars=False)


class ProgressBar(QThread):
    def __init__(self, mainWindow, async_pars=True, parent=None):
        super().__init__()
        self.mainWindow = mainWindow
        self.async_pars = async_pars

    def run(self):
        if self.async_pars:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.run(self.mainWindow.parser_start(dict_data=self.mainWindow.default_val))
        else:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.run(self.mainWindow.parser_start(dict_data=self.mainWindow.default_val, async_pars=False))


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec())
