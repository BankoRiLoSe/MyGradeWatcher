import requests
import time
import base64
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr  # === 新增：用于标准化邮件地址 ===
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5 as Cipher_pkcs1_v1_5

# ================= 配置区域 =================
USERNAME = "231210400308"
PASSWORD = "******"
# 接收通知的邮箱
MAIL_USER = "2089058985@qq.com"
MAIL_PASS = "*******"
RECEIVER = "mh2089058985@gmail.com"


# ===========================================

def get_rsa_int(content):
    try:
        missing_padding = len(content) % 4
        if missing_padding: content += '=' * (4 - missing_padding)
        return int.from_bytes(base64.b64decode(content), byteorder='big')
    except:
        return int(content, 16)


def encrypt_password(password, modulus, exponent):
    rsa_key = RSA.construct((modulus, exponent))
    cipher = Cipher_pkcs1_v1_5.new(rsa_key)
    return base64.b64encode(cipher.encrypt(password.encode())).decode()


def send_mail(new_courses):
    if "你的QQ" in MAIL_USER:
        print("【提示】邮箱未配置，跳过发送。")
        return

    content = "检测到成绩更新：\n\n"
    for course in new_courses:
        # 兼容一下有时候学分可能为空的情况
        score = course.get('cj', '未知')
        credit = course.get('xf', '未知')
        content += f"课程：{course['kcmc']}\n成绩：{score}\n学分：{credit}\n------------------\n"

    msg = MIMEText(content, 'plain', 'utf-8')

    # === 关键修复：使用 formataddr 生成符合 RFC 标准的头部 ===
    # 格式会变成： "GradeBot <123456@qq.com>"
    msg['From'] = formataddr(["GradeBot", MAIL_USER])
    msg['To'] = formataddr(["Student", RECEIVER])

    msg['Subject'] = Header(f"【新成绩】{new_courses[0]['kcmc']} 等{len(new_courses)}门", 'utf-8')

    try:
        smtpObj = smtplib.SMTP_SSL("smtp.qq.com", 465)
        smtpObj.login(MAIL_USER, MAIL_PASS)
        smtpObj.sendmail(MAIL_USER, [RECEIVER], msg.as_string())
        print(">>> 邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")


def run():
    base_url = "https://jwglxt.haut.edu.cn/jwglxt"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"})

    try:
        print("1. 正在登录...")
        session.get(f"{base_url}/xtgl/login_slogin.html")
        key_res = session.get(f"{base_url}/xtgl/login_getPublicKey.html?time={int(time.time() * 1000)}").json()
        encrypted_pw = encrypt_password(PASSWORD, get_rsa_int(key_res['modulus']), get_rsa_int(key_res['exponent']))

        login_data = {"yhm": USERNAME, "url": "/cjcx/cjcx_cxXsgrcj.html", "mm": encrypted_pw}
        login_res = session.post(f"{base_url}/xtgl/login_slogin.html?time={int(time.time() * 1000)}", data=login_data)

        if "用户名或密码不正确" in login_res.text:
            print("登录失败！")
            return

        print("2. 登录成功，正在获取所有历史成绩...")

        # 获取所有历史成绩
        query_data = {
            "xnm": "",
            "xqm": "",
            "_search": "false",
            "nd": int(time.time() * 1000),
            "queryModel.showCount": "500",
            "queryModel.currentPage": "1",
            "queryModel.sortOrder": "desc",
            "queryModel.sortName": "xnm",
            "time": "0"
        }

        grade_url = f"{base_url}/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005"
        grade_res = session.post(grade_url, data=query_data)

        try:
            items = grade_res.json().get('items', [])
        except:
            print("解析JSON失败，可能被拦截或Session失效")
            return

        print(f"共获取到 {len(items)} 条历史成绩记录。正在筛选本学期(2025)...")

        # 读取缓存
        old_ids = []
        if os.path.exists("grade_cache.txt"):
            with open("grade_cache.txt", "r", encoding="utf-8") as f:
                old_ids = f.read().split(",")

        new_courses = []
        current_ids = []

        # 筛选逻辑
        for item in items:
            if str(item.get('xnm')) == "2025":
                # 组合ID
                cid = f"{item.get('kch_id')}_{item.get('kcmc')}_{item.get('cj')}"
                current_ids.append(cid)

                print(f"--> [2025] {item['kcmc']} | {item['cj']}分")

                # 如果不在缓存里，或者是第一次运行（缓存文件不存在），则加入通知列表
                if cid not in old_ids:
                    new_courses.append(item)

        # 只有当发现新课时才操作
        if new_courses:
            print(f"\n发现 {len(new_courses)} 门新出分课程！正在发送邮件...")
            send_mail(new_courses)

            # 更新缓存：把当前所有2025的课程都记下来
            # 注意：这里我们采用追加写入还是覆盖？
            # 建议：既然 current_ids 包含了当前网页上所有的 2025 课程，
            # 我们应该要把 old_ids 里属于以前年份的保留下来（如果有的话），
            # 或者简单点，我们只记录所有的历史ID。

            # 修正缓存逻辑：将本次发现的新课ID追加到缓存文件中
            with open("grade_cache.txt", "a", encoding="utf-8") as f:
                if os.path.getsize("grade_cache.txt") > 0:
                    f.write(",")
                f.write(",".join([f"{c['kch_id']}_{c['kcmc']}_{c['cj']}" for c in new_courses]))

        else:
            print("\n没有发现新发布的成绩（和上次缓存一致）。")

    except Exception as e:
        print(f"运行出错: {e}")


if __name__ == "__main__":
    run()
