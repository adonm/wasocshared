from pathlib import Path
from itertools import groupby
from dateutil.parser import parse
import requests
from bs4 import BeautifulSoup
from diskcache import Index

macro_cache = Index()

def define_env(env):
    """
    This is the hook for defining variables, macros and filters

    - variables: the dictionary that contains the environment variables
    - macro: a decorator function, to declare a macro.
    """

    def get_title(path):
        line = ""
        with open(path) as f:
            while not line.startswith("#"):
                line = f.readline()
        return line[2:].strip()

    @env.macro
    def date_index(folder, prefix="", expand=3, include=None):
        """
        Insert an index to a glob pattern relative to top dir of documentation project.
        """
        glob = f"{folder}/*.md"
        cachekey = f"date_index.{glob}.{prefix}.{expand}.{include}"
        if cachekey in macro_cache:
            return macro_cache[cachekey]
        files = Path(env.project_dir).glob(glob)
        mdtext = []
        # Reverse order, sorted by first 6 characters (year + month)
        months = groupby(reversed(sorted(files)), key=lambda f: f.name[0:6])
        month_count = 0
        for month, paths in months:
            month_text = parse(month + "01").strftime("%Y %B")
            if month_count < expand:
                indent = ""
                mdtext.append(f"#### {month_text}")
            else:
                indent = "    "
                mdtext.append(f'??? note "{month_text}"')
            mdtext.append("")
            for path in paths:
                title = get_title(path)
                mdtext.append(f"{indent}- [{title}]({prefix}{path.name})")
            month_count += 1
            if include is not None:
                if month_count > include:
                    break
        macro_cache[cachekey] = "\n".join(mdtext)
        return macro_cache[cachekey]


    def getCategory(mitreID):
        category = mitreID[:2]

        if (category[:2] == "TA"):
            return "tactics"
        elif (category[:1] == "T"):
            return f"techniques"
        elif (category[:1] == "S"):
            return "software"
        elif (category[:1] == "G"):
            return "groups"
        elif (category[:1] == "C"):
            return "campaigns"
        else:
            return None

    @env.macro
    def mitre(mitreId):
        cachekey = f"mitre.{mitreId}"
        if cachekey in macro_cache:
            return macro_cache[cachekey]

        try: 
            techRef = mitreId.replace(".","/") # Prep for url
            category = getCategory(mitreId)
            url = f"https://attack.mitre.org/{category}/{techRef}/"

            response = requests.get(url)

            if response.status_code == 200:
                bsoup = BeautifulSoup(response.text, 'html.parser')

                #Find the technique heading and retrieve content
                desired_elements = bsoup.find_all('h1')

                # Get the text bit from the list without the HTML tags
                heading = [element.get_text() for element in desired_elements]

                # Combine the technique ID with the technique heading
                combinedText = ''.join(mitreId) + ' -' + ''.join(heading)

                # Return it as a link
                macro_cache[cachekey] = f"[{combinedText}]({url})"
                return macro_cache[cachekey] 
            
            else:
                return f"Failed to fetch content from the {mitreId}. Status code: {response.status_code}"
            
        except Exception as e:
            return f"An error occurred while fetching content from {mitreId}: {str(e)}"