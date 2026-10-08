from pathlib import Path
from bs4 import BeautifulSoup


def convert_bad_to_good(input_file_path: str, output_file_path: str):
    input_path = Path(input_file_path)

    if not input_path.exists():
        print(f"Error: Could not find '{input_file_path}'")
        return

    html_content = input_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html_content, "lxml")

    # converts the h2 to h1 as this is better for screenreaders
    h2_tag = soup.find("h2")
    if h2_tag:
        h1_tag = soup.new_tag("h1")
        big_h1 = soup.new_tag("big")
        big_h1.string = h2_tag.get_text(strip=True)
        h1_tag.append(big_h1)
        h2_tag.replace_with(h1_tag)

    form = soup.find("form")
    if form:
        # Convert all <div> elements into <label> elements with <big> tags to ensure easier for screenreaders to parse
        for div in form.find_all("div"):
            # Find the input or select tag directly following this div
            input_tag = div.find_next_sibling(["input", "select"])
            if input_tag and input_tag.has_attr("id"):
                element_id = input_tag["id"]
                # Create <label for="...">
                label_tag = soup.new_tag("label")
                label_tag["for"] = element_id

                # Wrap text inside <big>
                big_tag = soup.new_tag("big")
                big_tag.string = div.get_text(strip=True) + ":"
                label_tag.append(big_tag)

                div.replace_with(label_tag)

        # Convert <select> dropdown into an <input type="text">
        select_tag = form.find("select")
        if select_tag:
            select_id = select_tag.get("id", "number")

            # FIXED: Create tag first, then set HTML attributes on the object
            new_input = soup.new_tag("input")
            new_input["type"] = "text"
            new_input["id"] = select_id
            new_input["name"] = select_id

            select_tag.replace_with(new_input)

    # Automatically create and write to good_website.html
    output_path = Path(output_file_path)
    output_path.write_text(soup.prettify(), encoding="utf-8")

    print(f"Success! Created '{output_file_path}' from '{input_file_path}'")


if __name__ == "__main__":
    convert_bad_to_good("bad_website\\bad_website.html", "good_website/good_website.html")