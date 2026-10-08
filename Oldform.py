# we are using pip 3.12, if this arises any compatability issues when it comes to parsing
from pathlib import Path
from bs4 import BeautifulSoup
def get_html(path_to_page : str):
    file_path = Path(path_to_page)
    html_content = file_path.read_text(encoding = "utf-8")
    soup = BeautifulSoup(html_content, 'lxml') # i chose lxml over http parser as this tends to perform
    # better with forms
    form = soup.find("form")
    if form == None:
        print("Can't find a form")
    form_html = str(form)
    form_text = form.get_text(separator = "\n", strip = True)
    print(form_html)
    print("\nForm text")
    print(form_text)
get_html("bad_website\\bad_website.html")
