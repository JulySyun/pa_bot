import asyncio
import json
import os
from datetime import datetime

import gspread
import uvicorn
import re

from fastapi import FastAPI, Request, HTTPException
from fastapi import Query
from gspread.utils import ValueInputOption

from pydantic import BaseModel
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent, FollowEvent, PostbackEvent
)

from google.oauth2.service_account import Credentials

from dotenv import load_dotenv
from pathlib import Path

# 新增助理、我要新增事項
# 事件、觸發時間、提醒頻率(天)
# 先掃觸發時間 => 尚未到達 => 跳過
# 先掃觸發時間 => 時間到 => 讀取提醒頻率 =>將觸發時間欄位 修改 下次要觸發的時間

app = FastAPI()
load_dotenv()

class LineSetting:
    def __init__(self):
        self.LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
        self.configuration = Configuration(access_token=self.LINE_CHANNEL_ACCESS_TOKEN)
        self.handler = WebhookHandler(self.LINE_CHANNEL_SECRET)
        self.api_client = ApiClient(configuration=self.configuration)
        self.messaging_api = MessagingApi(self.api_client)

class GSheetSetting:
    def __init__(self):
        self.SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]

        # if os.getenv("ENV") == "LOCAL":
        #     search_dir = Path("")
        # else:
        #     search_dir = Path("api")
        #
        # matches = [f for f in search_dir.iterdir() if f.is_file() and "pa-bot" in f.name and f.suffix==".json"]
        # self.SERVICE_ACCOUNT_FILE = str(matches[0])


        sa_json = os.environ.get("GSPREAD_SA_JSON")

        creds = json.loads(sa_json)
        gc = gspread.service_account_from_dict(creds)

        # cd = Credentials.from_service_account_file(
        #     self.SERVICE_ACCOUNT_FILE, scopes=self.SCOPES
        # )

        # gc = gspread.authorize(cd)

        self.spreadsheet = gc.open_by_key(os.getenv("SPREADSHEET_ID_FOR_CUSTOMER"))

class Event(BaseModel):
    userId: str
    eventName: str
    eventDate: str

class DateRule:
    def __init__(self):
        # 日期(有斜線):2025/09/02
        self.date_pattern_slash = r"^\d{4}/(0?[1-9]|1[0-2])/(0?[1-9]|[12][0-9]|3[01])$"

        # 日期(無斜線):20250902
        self.date_pattern_noslash = r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])$"

        # 日期(有斜線) + 時間: 2025/09/02 13:10
        self.date_pattern_slash_time = r"^\d{4}/(0?[1-9]|1[0-2])/(0?[1-9]|[12][0-9]|3[01])\s(0?[0-9]|1\d|2[0-3]):?([0-5]?\d):?([0-5]?\d)?$"

        # 日期(無斜線) + 時間: 20250902 13:10
        self.date_pattern_noslash_time = r"^\d{4}(0?[1-9]|1[0-2])(0?[1-9]|[12][0-9]|3[01])\s(0?[0-9]|1\d|2[0-3]):?([0-5]?\d):?([0-5]?\d)?$"

        # 只有時間
        self.nodate_time = r"^(0?[0-9]|1\d|2[0-3]):?([0-5]?\d):?([0-5]?\d)?$"


    def date_match(self, input_date):

        input_date = input_date.strip()

        input_split = input_date.split(" ")
        try:
            if len(input_split) == 1:

                # 日期(有斜線):2025/09/02   回傳=> 2025/09/02 00:00
                if re.match(self.date_pattern_slash, input_date):
                    dt = datetime.strptime(input_date, "%Y/%m/%d")
                    return dt.strftime("%Y/%m/%d 00:00:00")

                # 日期(無斜線):20250902 => 回傳 2025/09/02 00:00
                elif re.match(self.date_pattern_noslash, input_date):
                    dt = datetime.strptime(input_date, "%Y%m%d")
                    return dt.strftime("%Y/%m/%d 00:00:00")

                # 00:00:00
                elif re.match(self.nodate_time, input_date):
                    fmt = self.get_time_fmt(input_split[0])
                    if not fmt: return fmt

                    today = datetime.today().strftime("%Y/%m/%d")
                    dt = datetime.strptime(f"{today} {input_date}", f"%Y/%m/%d {fmt}")
                    return dt.strftime("%Y/%m/%d %H:%M:%S")


            else:
                #01:01、01:01:01、0101、010101
                fmt = self.get_time_fmt(input_split[1])
                if not fmt: return fmt


                # 日期(有斜線):2025/09/02 13:01  回傳=> 2025/09/02 13:01
                if re.match(self.date_pattern_slash_time, input_date):
                    dt = datetime.strptime(input_date, f"%Y/%m/%d {fmt}")
                    return dt.strftime("%Y/%m/%d %H:%M:%S")

                # 日期(無斜線):20250902 13:01  回傳=> 2025/09/02 13:01
                elif re.match(self.date_pattern_noslash_time, input_date):
                    dt = datetime.strptime(input_date, f"%Y%m%d {fmt}")
                    return dt.strftime("%Y/%m/%d %H:%M:%S")

                else:
                    return False

        except (Exception,) as e:
            print(f"!!!!!! {e}")
            return False


    def get_time_fmt(self, input_time):
        input_split = input_time.split(":")
        print(input_split)
        if len(input_split) == 1:

            if len(input_split[0]) == 4:
                fmt = "%H%M"
            elif len(input_split[0]) == 6:
                fmt = "%H%M%S"
            else:
                return False

        elif len(input_split) == 2:
            fmt = "%H:%M"
        elif len(input_split) == 3:
            fmt = "%H:%M:%S"
        else:
            return False

        return fmt

line = LineSetting()
gs = GSheetSetting()
dr = DateRule()
user_state = {}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    print(body)
    try:
        # line.handler.handle(body.decode("utf-8"), signature)
        await asyncio.to_thread(line.handler.handle, body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except (Exception,) as e :
        raise HTTPException(status_code=500, detail=f"Internal server error!!: {str(e)}")

    return "OK"


# 訊息事件處理
@line.handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text
    user_id = event.source.user_id
    print(f"收到使用者訊息：{user_msg}")

    if user_id not in user_state:
        if user_msg == "help":
            reply_msg = ("可以在對話框中輸入以下指令:\n\n"
                         "➡格式為 事務名稱 日期 時間\n\n"
                         "正確指令:\n"
                         "打掃 20250901 13:30\n\n"
                         "默認指令:\n"
                         "打掃 20250901\n"
                         "(當沒有輸入時間則默認00:00)\n\n"
                         "錯誤指令:\n"
                         "指輸入事務名稱或只輸入時間，則無效")
        else:
            try:
                pack = user_msg.split(" ", 1)
                if len(pack) != 2:
                    reply_msg = "不符合格式"
                    reply_message(event, reply_msg)
                    return

                event_name, event_data = pack
                event_data = dr.date_match(event_data)


                if not event_data:
                    reply_msg = "不符合格式"
                    reply_message(event, reply_msg)

                else:
                    reply_msg = (f"收到您的事物請求:{user_msg}\n"
                                 f"請問提醒頻率為何?\n\n"
                                 f"(例如: 1月、2天、3小時、5分\n"
                                 f"如不輸入請填0)")

                    reply_message(event, reply_msg)

                    user_state[user_id] = ["wait_to_record", event_name, event_data]

            except (Exception,) as e:
                print(e)
                reply_msg = "格式錯誤"
                reply_message(event, reply_msg)


    else:
        try:
            # 使用者準備要記錄事務
            if user_state[user_id][0] == "wait_to_record":
                # 使用者回答
                if any(kw in user_msg for kw in ["退", "離開", "退出"]):
                    reply_message(event, "已離開此次對話")

                else:
                    isExist_freq = False
                    for kw in ["個月", "月", "天", "個小時", "小時", "時", "分"]:
                        if kw in user_msg:
                            try:
                                freq = user_msg.split(kw)[0]
                                if kw == "個月":
                                    unit = "月"
                                elif kw == "個小時" or kw == "小時":
                                    unit = "時"
                                else:
                                    unit = kw
                                ws = gs.spreadsheet.worksheet(f"UserID-{user_id}")
                                ws.append_row([user_state[user_id][1], user_state[user_id][2], f"{freq}{unit}"],
                                              value_input_option=ValueInputOption.user_entered)

                                reply_message(event, "完成事件的紀錄!\n"
                                                     f"事件名稱:{user_state[user_id][1]}\n"
                                                     f"觸發時間:{user_state[user_id][2]}\n"
                                                     f"執行頻率:{freq}{unit}")
                                isExist_freq = True
                                break

                            except ValueError:
                                reply_message(event, "您輸入的不是有效數字，請重新輸入")
                                return

                    if not isExist_freq:
                        ws = gs.spreadsheet.worksheet(f"UserID-{user_id}")
                        ws.append_row([user_state[user_id][1], user_state[user_id][2]],
                                      value_input_option=ValueInputOption.user_entered)
                        reply_message(event, "完成事件的紀錄!\n"
                                             f"事件名稱:{user_state[user_id][1]}\n"
                                             f"觸發時間:{user_state[user_id][2]}\n"
                                             f"執行頻率: 無")

                print(user_state)
                del user_state[user_id]
                print(user_state)

        except (Exception,) as e:
            print(f"錯誤!{e}")


#加入好友，自動回覆
@line.handler.add(FollowEvent)
def handle_follow(event):
    reply_msg = ("您好!\n"
                 "➡︎歡迎使用日常生活助理\n\n"
                 "➡︎這是一個可以提醒你生活瑣事的事件助理!\n\n"
                 "➡︎剛加入的朋友可以先從新增或閱讀幫助開始哦\n\n"
                 "💬輸入help可以查閱指令")

    reply_message(event, reply_msg)


@line.handler.add(PostbackEvent)
def handle_postback(event):
    tag = event.postback.data
    user_id = event.source.user_id
    if tag == "action=Create":
        try:
            ws = gs.spreadsheet.worksheet(f"UserID-{user_id}")
            reply_message(event, "您已經建立過提醒助理囉!")

        except gspread.WorksheetNotFound:
            ws = gs.spreadsheet.add_worksheet(title=f"UserID-{user_id}", rows=100, cols=4)
            ws.append_row(["事件名稱", "觸發時間"])
            reply_message(event, "建立完成!")

    elif tag == "action=CheckAll":
        try:
            ws = gs.spreadsheet.worksheet(f"UserID-{user_id}")
            records = ws.get_all_records()
            msg = ""
            for index, record in enumerate(records):
                if index != len(records)-1:
                    msg += record["事件名稱"] + ":" + record["觸發時間"]+"\n\n"
                else:
                    msg += record["事件名稱"] + ":" + record["觸發時間"]

            reply_message(event, msg)


        except gspread.WorksheetNotFound:
            reply_message(event, "提醒助理尚未建立，故無法查詢!")

#回覆的方法
def reply_message(event, reply_msg):
    reply_request = ReplyMessageRequest(
        reply_token=event.reply_token,
        messages=[TextMessage(text=reply_msg)]
    )
    line.messaging_api.reply_message_with_http_info(reply_request)


# def push_message(self, user_id, message):
#     self.messaging_api.push_message(
#         PushMessageRequest(
#             to=user_id,
#             messages=[TextMessage(text=message)]
#         )
#     )


@app.post("/")
async def root():
    return {"message":"Connected successfully!"}



@app.post("/root_post3")
async def root_post(name:str = Query(...)):
    res = {"message": "OK123"}
    print(f"1.收到結果:{name}")
    print(f"2.回傳結果:{res}")

    return {"message": "OK123"}

@app.post("/push_user")
async def push_user(event:Event):
    print(f"收到 {event.userId}, {event.eventName}, {event.eventDate}")
    return f"收到 {event.userId}, {event.eventName}, {event.eventDate}"




if __name__ == "__main__":
    # uvicorn index:app --host 0.0.0.0 --port 5000 --reload
    # uvicorn app:app --host 0.0.0.0 --port 5000 --reloaduvicorn app:app --host 0.0.0.0 --port 5000 --reload
    uvicorn.run("index:app", host="0.0.0.0", port=5000, reload=True)
