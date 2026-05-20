import base64
import os
import smtplib
import sys
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import requests
from Crypto.Cipher import PKCS1_v1_5 as Cipher_pkcs1_v1_5
from Crypto.PublicKey import RSA

USERNAME = os.getenv("GRADE_USERNAME", "")
PASSWORD = os.getenv("GRADE_PASSWORD", "")
MAIL_USER = os.getenv("MAIL_USER", "")
MAIL_PASS = os.getenv("MAIL_PASS", "")
RECEIVER = os.getenv("MAIL_RECEIVER", "")
TARGET_XNM = os.getenv("TARGET_XNM", "")
CACHE_FILE = "grade_cache.txt"
BASE_URL = "https://jwglxt.haut.edu.cn/jwglxt"


def get_rsa_int(content):
    try:
        missing_padding = len(content) % 4
        if missing_padding:
            content += "=" * (4 - missing_padding)
        return int.from_bytes(base64.b64decode(content), byteorder="big")
    except Exception:
        return int(content, 16)


def encrypt_password(password, modulus, exponent):
    rsa_key = RSA.construct((modulus, exponent))
    cipher = Cipher_pkcs1_v1_5.new(rsa_key)
    return base64.b64encode(cipher.encrypt(password.encode())).decode()


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
    return set(filter(None, content.split(",")))


def save_cache(ids):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(",".join(sorted(ids)))


def send_mail(new_courses):
    if not (MAIL_USER and MAIL_PASS and RECEIVER):
        print("邮箱配置不完整，跳过发送。")
        return

    content = "检测到成绩更新：\n\n"
    for course in new_courses:
        content += (
            f"课程：{course.get('kcmc', '未知')}\n"
            f"成绩：{course.get('cj', '未知')}\n"
            f"学分：{course.get('xf', '未知')}\n"
            "------------------\n"
        )

    msg = MIMEText(content, "plain", "utf-8")
    msg["From"] = formataddr(("GradeBot", MAIL_USER))
    msg["To"] = formataddr(("Student", RECEIVER))
    msg["Subject"] = Header(f"共 {len(new_courses)} 门", "utf-8")

    with smtplib.SMTP_SSL("smtp.qq.com", 465) as smtp:
        smtp.login(MAIL_USER, MAIL_PASS)
        smtp.sendmail(MAIL_USER, [RECEIVER], msg.as_string())

    print(">>> 邮件发送成功！")


def run():
    if not USERNAME or not PASSWORD:
        print("缺少 GRADE_USERNAME 或 GRADE_PASSWORD")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    })

    print("1. 正在登录...")
    session.get(f"{BASE_URL}/xtgl/login_slogin.html", timeout=10).raise_for_status()

    key_res = session.get(
        f"{BASE_URL}/xtgl/login_getPublicKey.html?time={int(time.time() * 1000)}",
        timeout=10,
    )
    key_res.raise_for_status()
    key_data = key_res.json()

    encrypted_pw = encrypt_password(
        PASSWORD,
        get_rsa_int(key_data["modulus"]),
        get_rsa_int(key_data["exponent"]),
    )

    login_data = {
        "yhm": USERNAME,
        "url": "/cjcx/cjcx_cxXsgrcj.html",
        "mm": encrypted_pw,
    }
    login_res = session.post(
        f"{BASE_URL}/xtgl/login_slogin.html?time={int(time.time() * 1000)}",
        data=login_data,
        timeout=10,
    )
    login_res.raise_for_status()

    if "用户名或密码不正确" in login_res.text:
        print("登录失败：用户名或密码不正确")
        sys.exit(1)

    print("2. 登录成功，正在获取成绩...")
    grade_url = f"{BASE_URL}/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005"
    query_data = {
        "xnm": "",
        "xqm": "",
        "_search": "false",
        "nd": int(time.time() * 1000),
        "queryModel.showCount": "500",
        "queryModel.currentPage": "1",
        "queryModel.sortOrder": "desc",
        "queryModel.sortName": "xnm",
        "time": "0",
    }

    grade_res = session.post(grade_url, data=query_data, timeout=10)
    grade_res.raise_for_status()
    items = grade_res.json().get("items", [])

    old_ids = load_cache()
    current_ids = set()
    new_courses = []

    for item in items:
        xnm = str(item.get("xnm", ""))
        if TARGET_XNM and xnm != TARGET_XNM:
            continue

        cid = f"{item.get('kch_id')}_{item.get('kcmc')}_{item.get('cj')}"
        current_ids.add(cid)

        if cid not in old_ids:
            new_courses.append(item)

    print(f"本次筛选到 {len(current_ids)} 条成绩记录。")

    if new_courses:
        print(f"发现 {len(new_courses)} 门新出分课程，正在发送邮件...")
        send_mail(new_courses)
    else:
        print("没有发现新发布的成绩。")

    save_cache(current_ids)


if __name__ == "__main__":
    run()
