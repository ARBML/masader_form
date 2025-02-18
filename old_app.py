import streamlit as st
import requests
import re
import json
import os
import subprocess
from github import Github
from git import Repo
from datetime import date
from constants import *

from dotenv import load_dotenv

MASADER_BOT_URL = "https://masaderbot-production.up.railway.app/run"

st.set_page_config(
    page_title="Masader Form",
    page_icon="📮",
    initial_sidebar_state="collapsed",
)
"# 📮 :rainbow[Masader Form]"

load_dotenv()  # Load environment variables from a .env file
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GIT_USER_NAME = os.getenv("GIT_USER_NAME")
GIT_USER_EMAIL = os.getenv("GIT_USER_EMAIL")


def validate_github(username):
    response = requests.get(f"https://api.github.com/users/{username}")
    if response.status_code == 200:
        return True
    else:
        return False


def validate_url(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.ConnectionError:
        return False


def validate_dataname(name: str) -> bool:
    """
    Validates the name of the dataset.

    Args:
        name (str): The name of the dataset.

    Returns:
        bool: True if valid, False otherwise.
    """

    for char in name.lower():
        if char not in VALID_SYMP_NAMES:
            st.error(f"Invalid character in the dataset name {char}")
            return False
    return True


def validate_comma_separated_number(number: str) -> bool:
    """
    Validates a number with commas separating thousands.

    Args:
        number (str): The number as a string.

    Returns:
        bool: True if valid, False otherwise.
    """
    # Regular expression pattern to match numbers with comma-separated thousands
    pattern = r"^\d{1,3}(,\d{3})*$"

    # Match the pattern
    return bool(re.fullmatch(pattern, number))


def update_session_config(json_data):
    for key in json_data:
        if key in ["Year"]:
            try:
                st.session_state[key] = int(json_data[key])
            except:
                st.session_state[key] = 2024
        elif key in ["Collection Style", "Domain"]:
            values = [val.strip() for val in json_data[key].split(",")]
            acc_values = []

            # if some values are not legitimate, use other instead
            for value in values:
                if value in column_options[key].split(","):
                    acc_values.append(value)

            if len(values) > len(acc_values):
                if "other" not in acc_values:
                    acc_values.append("other")

            st.session_state[key] = acc_values
        elif key == "Tasks":
            tasks = []
            other_tasks = []
            for task in [task.strip() for task in json_data[key].split(",")]:
                if task not in column_options["Tasks"].split(","):
                    other_tasks.append(task)
                else:
                    tasks.append(task)

            if len(other_tasks):
                st.session_state["Other Tasks"] = ",".join(other_tasks)

            if len(tasks):
                st.session_state["Tasks"] = tasks

        elif key == "Subsets":
            for i, subset in enumerate(json_data[key]):
                for subkey in subset:
                    st.session_state[f"subset_{i}_{subkey.lower()}"] = json_data[key][
                        i
                    ][subkey]
        else:
            st.session_state[key] = json_data[key].strip()


def reload_config(json_data):
    if "metadata" in json_data:
        json_data = json_data["metadata"]
    update_session_config(json_data)
    st.session_state.show_form = True


def render_form():
    i = 0

    while True:
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        with col1:
            name = st.text_input("Name:", key=f"subset_{i}_name")
        with col3:
            volume = st.text_input("Volume", key=f"subset_{i}_volume")
        with col2:
            dialect = st.selectbox(
                "Dialect",
                column_options["Dialect"].split(","),
                key=f"subset_{i}_dialect",
            )
        with col4:
            unit = st.selectbox(
                "Unit", column_options["Unit"].split(","), key=f"subset_{i}_unit"
            )
        if name:
            i += 1
        else:
            break


def update_pr(new_dataset):
    PRS = []
    if os.path.exists("prs.json"):
        with open("prs.json", "r") as f:
            PRS = json.load(f)
    else:
        with open("prs.json", "w") as f:
            json.dump(PRS, f, indent=4)

    # create a valid name for the dataset
    data_name = new_dataset["Name"].lower().strip()
    for symbol in VALID_PUNCT_NAMES:
        data_name = data_name.replace(symbol, "_")

    # Configuration
    REPO_NAME = "ARBML/masader"  # Format: "owner/repo"
    BRANCH_NAME = f"add-{data_name}"
    PR_TITLE = f"Adding {new_dataset['Name']} to the catalogue"
    PR_BODY = f"This is a pull request by @{st.session_state['gh_username']} to add a {new_dataset['Name']} to the catalogue."

    # Initialize GitHub client
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    # setup name and email
    os.system(f"git config --global user.email {GIT_USER_EMAIL}")
    os.system(f"git config --global user.name {GIT_USER_NAME}")

    # Clone repository
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{REPO_NAME}.git"
    local_path = "./temp_repo"

    pr_exists = False

    # check the list of Pull Requests
    for pr in PRS:
        pr_obj = repo.get_pull(pr["number"])

        # check the branch if it exists
        if pr["branch"] == BRANCH_NAME:
            print("PR already exists")
            pr_exists = True
        else:
            #  delete unused branches
            if pr["state"] == "open":
                if pr_obj.state == "closed":
                    # repo.get_git_ref(f"heads/{pr['branch']}").delete() # might be risky
                    pr["state"] = "closed"

    if os.path.exists(local_path):
        subprocess.run(["rm", "-rf", local_path])  # Clean up if exists
    Repo.clone_from(repo_url, local_path)

    # Modify file
    local_repo = Repo(local_path)

    FILE_PATH = f"datasets/{data_name}.json"

    # if the branch exists
    if pr_exists:
        local_repo.git.checkout(BRANCH_NAME)
        local_repo.git.pull("origin", BRANCH_NAME)
        with open(f"{local_path}/{FILE_PATH}", "w") as f:
            json.dump(new_dataset, f, indent=4)
        local_repo.git.add(FILE_PATH)
        # check if changes made
        if local_repo.is_dirty():
            local_repo.git.commit("-m", f"Updating {FILE_PATH}")
            local_repo.git.push("origin", BRANCH_NAME)
        else:
            st.info("No changes made to the dataset")
            return
    else:
        with open(f"{local_path}/{FILE_PATH}", "w") as f:
            json.dump(new_dataset, f, indent=4)
        local_repo.git.checkout("-b", BRANCH_NAME)
        local_repo.git.pull("origin", "main")
        # Commit and push changes
        local_repo.git.add(FILE_PATH)
        local_repo.git.commit("-m", f"Creating {FILE_PATH}.json")
        local_repo.git.push("--set-upstream", "origin", BRANCH_NAME)

    # if the PR doesn't exist
    if not pr_exists:
        pr = repo.create_pull(
            title=PR_TITLE,
            body=PR_BODY,
            head=BRANCH_NAME,
            base=repo.default_branch,
        )
        st.success(f"Pull request created: {pr.html_url}")
        # add the pr
        PRS.append(
            {
                "name": new_dataset["Name"],
                "url": pr.html_url,
                "branch": BRANCH_NAME,
                "state": "open",
                "number": pr.number,
            }
        )
    else:
        st.success(f"Pull request updated")

    with open("prs.json", "w") as f:
        json.dump(PRS, f, indent=4)

    st.balloons()


def load_json(url, link="", pdf=None):
    # Make the GET request to fetch the JSON data
    if link != "":
        response = requests.post(url, data={"link": link})
    elif pdf:
        response = requests.post(url, files={"file": pdf})
    else:
        response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON content
        json_data = response.json()
        reload_config(json_data)
        return True
    else:
        st.error(response.text)
    return False


def reset_config():
    with open("default.json", "r") as f:
        reload_config(json.load(f))
    st.session_state.show_form = False


@st.fragment()
def final_state():
    col1, col2 = st.columns(2)

    with col1:
        submit = st.form_submit_button("Submit")
    with col2:
        save = st.form_submit_button("Save")

    if submit or save:
        if not validate_github(st.session_state["gh_username"].strip()):
            st.error("Please enter a valid GitHub username.")
        elif not validate_dataname(st.session_state["Name"]):
            st.error("Please enter a valid dataset name.")
        elif not validate_url(st.session_state["Link"]):
            st.error("Please enter a valid repository link.")
        elif not st.session_state["License"].strip():
            st.error("Please select a valid license.")
        elif not st.session_state["Dialect"]:
            st.error("Please enter a valid dialect.")
        elif not st.session_state["Domain"]:
            st.error("Please select a valid domain.")
        elif not st.session_state["Collection Style"]:
            st.error("Please select a valid collection style")
        elif (
            not st.session_state["Description"].strip()
            or len(st.session_state["Description"]) < 10
        ):
            st.error("Please enter a non empty (detailed) description of the dataset")
        elif not validate_comma_separated_number(st.session_state["Volume"].strip()):
            st.error("Please enter a valid volume. for example 1,000")
        elif not st.session_state["Unit"].strip():
            st.error("Please select a valid unit.")
        elif not st.session_state["Host"].strip():
            st.error("Please select a valid host.")
        elif not st.session_state["Tasks"]:
            st.error("Please select the Tasks.")
        elif not st.session_state["Added By"].strip():
            st.error("Please enter your full name.")
        else:
            config = create_json()
            if submit:
                update_pr(config)
            else:
                save_path = st.text_input(
                    "Save Path",
                    value=f"/Users/zaidalyafeai/Documents/Development/masader_bot/validset/{st.session_state['Name'].lower()}.json",
                    help="Enter the directory path to save the JSON file",
                )
                if save_path:
                    with open(save_path, "w") as f:
                        json.dump(config, f, indent=4)
                    st.success(f"Form saved successfully to {save_path}")


def create_json():
    config = {}
    columns = [
        "Name",
        "Subsets",
        "HF Link",
        "Link",
        "License",
        "Year",
        "Language",
        "Dialect",
        "Domain",
        "Form",
        "Collection Style",
        "Description",
        "Volume",
        "Unit",
        "Ethical Risks",
        "Provider",
        "Derived From",
        "Paper Title",
        "Paper Link",
        "Script",
        "Tokenized",
        "Host",
        "Access",
        "Cost",
        "Test Split",
        "Tasks",
        "Venue Title",
        "Citations",
        "Venue Type",
        "Venue Name",
        "Authors",
        "Affiliations",
        "Abstract",
        "Added By",
    ]
    for key in columns:
        if key == "Subsets":
            config["Subsets"] = []
            i = 0
            while True:
                subset = {}
                if f"subset_{i}_name" in st.session_state:
                    if st.session_state[f"subset_{i}_name"] != "":
                        subset["Name"] = st.session_state[f"subset_{i}_name"]
                        subset["Volume"] = st.session_state[f"subset_{i}_volume"]
                        subset["Dialect"] = st.session_state[f"subset_{i}_dialect"]
                        subset["Unit"] = st.session_state[f"subset_{i}_unit"]
                        config["Subsets"].append(subset)
                        i += 1
                        continue
                break
        elif key in ["Collection Style", "Domain"]:
            config[key] = ",".join(st.session_state[key])
        elif key == "Tasks":
            tasks = st.session_state[key]
            if st.session_state["Other Tasks"].strip() != "":
                tasks += st.session_state["Other Tasks"].split(",")
            config[key] = ",".join(tasks)
        else:
            config[key] = st.session_state[key]
    return config


def create_element(label, placeholder="", help="", key="", value="", options=[]):
    st.text(label)
    if key in [
        "Language",
        "Form",
        "Unit",
        "Ethical Risks",
        "Script",
        "Access",
        "Test Split",
        "Venue Type",
    ]:
        st.radio(key, options=options, key=key, label_visibility="collapsed")
    elif key in ["License", "Dialect", "Host"]:
        st.selectbox(key, options=options, key=key, label_visibility="collapsed")
    elif key in ["Domain", "Collection Style", "Tasks"]:
        if key == "Collection Style":
            with st.expander("See description"):
                st.caption(
                    """
                    - **crawling** the data has been collected using scripts to collect the data
                    - **human annotaiton** the data has been labeled by humans
                    - **machine annotation** the data has been labeled by a software i.e. MT, OCR, ...
                    - **LLM Generated** LLMs have been used to collect or annotate the data
                    - **manual curation** the data has been created manually. 
                """
                )
        st.multiselect(key, options=options, key=key, label_visibility="collapsed")
    elif key in ["Description", "Abstract", "Affiliations", "Authors"]:
        st.text_area(
            key,
            key=key,
            placeholder=placeholder,
            help=help,
            label_visibility="collapsed",
        )
    else:
        st.text_input(
            key,
            key=key,
            placeholder=placeholder,
            help=help,
            value=value,
            label_visibility="collapsed",
        )


def main():

    st.info(
        """
    This is a the Masader form to add datasets to [Masader](https://arbml.github.io/masader/) catalogue.
    Before starting, please make sure you read the following instructions:
    - There are three options
        - 🦚 Manual Annotation: You can have to insert all the metadata manually.
        - 🤖 AI Annotation: Insert the pdf/arxiv link to extract the metadata automatically. 
        - 🚥 Load Annotation: Use this option to load a saved metadata annotation. 
    - Check the dataset does not exist in the catelouge using the search [Masader](https://arbml.github.io/masader/search)
    - You have a valid GitHub username
    - You have the direct link to the dataset repository

    Once you submit the dataset, we will send a PR, make sure you follow up there if you have any questions. 
    If you have face any issues post them on [GitHub](https://github.com/arbml/masader/issues).
    """,
        icon="👾",
    )

    if "show_form" not in st.session_state:
        reset_config()

    if st.query_params:
        if st.query_params["json_url"]:
            load_json(st.query_params["json_url"])

    options = st.selectbox(
        "Annotation Options",
        ["🦚 Manual Annotation", "🤖 AI Annotation", "🚥 Load Annotation"],
        on_change=reset_config,
    )

    if options == "🚥 Load Annotation":
        upload_file = st.file_uploader(
            "Upload Json",
            help="You can use this widget to preload any dataset from https://github.com/ARBML/masader/tree/main/datasets",
        )
        json_url = st.text_input(
            "Path to json",
            placeholder="For example: https://raw.githubusercontent.com/ARBML/masader_form/refs/heads/main/shami.json",
        )

        if upload_file:
            json_data = json.load(upload_file)
            reload_config(json_data)
        elif json_url:
            load_json(json_url)
        else:
            reset_config()

    elif options == "🤖 AI Annotation":
        st.warning(
            "‼️ AI annotation uses LLMs to extract the metadata form papers. However, this approach\
                   is not reliable as LLMs can hellucinate and extract untrustworthy informations. \
                   Make sure you revise the generated metadata before you submit."
        )
        paper_url = st.text_input("Insert arXiv or direct pdf link")
        upload_pdf = st.file_uploader(
            "Upload PDF of the paper",
            help="You can use this widget to preload any dataset from https://github.com/ARBML/masader/tree/main/datasets",
        )

        if paper_url:
            if "arxiv" in paper_url:
                load_json(MASADER_BOT_URL, link=paper_url)
            else:
                response = requests.get(paper_url)
                response.raise_for_status()  # Raise an error for bad responses (e.g., 404)
                if response.headers.get("Content-Type") == "application/pdf":
                    pdf = (
                        paper_url.split("/")[-1],
                        response.content,
                        response.headers.get("Content-Type", "application/pdf"),
                    )
                    load_json(MASADER_BOT_URL, pdf=pdf)
                else:
                    st.error(
                        f"Cannot retrieve a pdf from the link. Make sure {paper_url} is a direct link to a valid pdf"
                    )

        elif upload_pdf:
            # Prepare the file for sending
            pdf = (upload_pdf.name, upload_pdf.getvalue(), upload_pdf.type)
            load_json(MASADER_BOT_URL, pdf=pdf)
        else:
            reset_config()
    else:
        st.session_state.show_form = True

    if st.session_state.show_form:
        with st.form(key="dataset_form"):
            create_element("GitHub username*", key="gh_username", value="zaidalyafeai")

            create_element(
                "Name of the dataset*",
                placeholder="Use a representative name of the dataset.",
                help="For example CALLHOME: Egyptian Arabic Speech Translation Corpus",
                key="Name",
            )

            with st.expander("Add dilaect subsets"):
                st.caption(
                    "Use this field to add dialect subsets of the dataset. For example if the dataset has 1,000 sentences in the Yemeni dialect.\
                           For example take a look at the [shami subsets](https://github.com/ARBML/masader/tree/main/datasets/shami.json)."
                )
                render_form()

            # Links
            create_element(
                "Link*", placeholder="The link must be accessible", key="Link"
            )

            create_element(
                "Huggingface Link",
                placeholder="for example https://huggingface.co/datasets/labr",
                help="for example https://huggingface.co/datasets/labr",
                key="HF Link",
            )

            # Dataset Properties
            create_element(
                "License*", options=column_options["License"].split(","), key="License"
            )

            current_year = date.today().year
            st.number_input(
                "Year*",
                min_value=2000,
                max_value=current_year,
                help="Year of publishing the dataset/paper",
                key="Year",
            )

            create_element(
                "Language*",
                options=column_options["Language"].split(","),
                key="Language",
            )

            create_element(
                "Dialect*",
                options=column_options["Dialect"].split(","),
                help="Used mixed if the dataset contains multiple dialects",
                key="Dialect",
            )

            create_element(
                "Domain*", options=column_options["Domain"].split(","), key="Domain"
            )

            create_element(
                "Form*", options=column_options["Form"].split(","), key="Form"
            )

            create_element(
                "Collection Style*",
                options=column_options["Collection Style"].split(","),
                key="Collection Style",
            )

            create_element(
                "Description*",
                placeholder="Description about the dataset and its contents.",
                help="brief description of the dataset",
                key="Description",
            )

            # Volume and Units
            create_element(
                "Volume*",
                placeholder="For example 1,000.",
                help="How many samples are in the dataset. Please don't use abbreviations like 10K",
                key="Volume",
            )

            create_element(
                "Unit*",
                options=column_options["Unit"].split(","),
                help="tokens usually used for ner, pos tagging, etc. sentences for sentiment analysis, documents for text modelling tasks",
                key="Unit",
            )

            create_element(
                "Ethical Risks",
                options=column_options["Ethical Risks"].split(","),
                help="social media datasets are considered mid risks as they might release personal information, others might contain hate speech as well so considered as high risk",
                key="Ethical Risks",
            )

            create_element(
                "Provider",
                placeholder="Name of institution i.e. NYU Abu Dhabi",
                key="Provider",
            )

            create_element(
                "Derived From",
                placeholder="What is the source dataset, i.e. Common Crawl",
                key="Derived From",
            )
            # Paper Information
            create_element(
                "Paper Title", placeholder="Full title of the paper", key="Paper Title"
            )

            create_element(
                "Paper Link",
                placeholder="Link to the pdf i.e. https://arxiv.org/pdf/2110.06744.pdf",
                key="Paper Link",
            )

            # Technical Details
            create_element(
                "Script*", options=column_options["Script"].split(","), key="Script"
            )

            create_element(
                "Tokenized*",
                options=column_options["Tokenized"].split(","),
                help="Is the dataset tokenized i.e. الرجل = ال رجل",
                key="Tokenized",
            )

            create_element(
                "Host*",
                options=column_options["Host"].split(","),
                help="The name of the repository that hosts the data. Use other if not in the options.",
                key="Host",
            )

            create_element(
                "Access*", options=column_options["Access"].split(","), key="Access"
            )

            create_element(
                "Cost",
                placeholder="If the access is With-Fee inser the cost, i.e. 1750 $",
                help="For example 1750 $",
                key="Cost",
            )

            create_element(
                "Test split*",
                options=column_options["Test Split"].split(","),
                help="Does the dataset have validation / test split",
                key="Test Split",
            )

            create_element(
                "Tasks*", options=column_options["Tasks"].split(","), key="Tasks"
            )

            create_element(
                "Other Tasks*",
                placeholder="Other tasks that don't exist in the Tasks options.",
                help="Make sure the tasks don't appear in the Tasks field",
                key="Other Tasks",
            )

            create_element(
                "Venue Title", placeholder="Venue shortcut i.e. ACL", key="Venue Title"
            )

            # Venue Type
            create_element(
                "Venue Type",
                options=column_options["Venue Type"].split(","),
                help="Select the type of venue",
                key="Venue Type",
            )
            # Venue Name
            create_element(
                "Venue Name",
                placeholder="Full name i.e. Association of Computational Linguistics",
                key="Venue Name",
            )

            # Authors
            create_element(
                "Authors", placeholder="Add all authors split by comma", key="Authors"
            )

            # Affiliations
            create_element(
                "Affiliations", placeholder="Enter affiliations", key="Affiliations"
            )

            # Abstract
            create_element(
                "Abstract",
                placeholder="Abstract of the published paper",
                key="Abstract",
            )

            create_element(
                "Full Name*", placeholder="Please Enter your full name", key="Added By"
            )
            final_state()


if __name__ == "__main__":
    main()
