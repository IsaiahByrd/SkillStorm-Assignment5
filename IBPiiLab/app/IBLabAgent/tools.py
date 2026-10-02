from langchain.tools import tool

@tool
def read_record():
    pass

@tool
def send_contact_detail():
    pass

TOOLS = [read_record, send_contact_detail]