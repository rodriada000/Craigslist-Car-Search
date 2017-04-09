#!/usr/bin/env python3
# Craistlist Scraper Bot
#  Adam Rodriguez
from lxml import etree
from bs4 import BeautifulSoup
from craigslist_scraper.scraper import scrape_html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import smtplib
import datetime
import time

# debug function to print out values when debugging is enabled
debugging = True
def debug(s):
    if debugging: print(s)
    return

class CraigSettings:
    """
    A class
    """
    def __init__(self, settings_file):
        """
        Open an xml file containing settings for the scraper bot and initialize variables.
        """
        self.cities = [] # any variable set to None will not be included in the search criteria
        self.cars = []
        self.hasPic = None
        self.minPrice = None
        self.maxPrice = None
        self.minYear = None
        self.maxYear = None
        self.minMiles = None
        self.maxMiles = None 
        self.titleStatus = None
        self.recipientEmail = None
        self.senderEmail = None
        self.senderPwd = None
        self.blacklist = [] # keywords found in titles. keyword found in title will exclude the result.
        self.viewedListings = [] # listings from previous days that have been sent
        self.urlsToSearch = []

        with open("settings.cfg") as settingsFile: # open and parse settings
            tree = etree.parse(settingsFile)
        
        root = tree.getroot()

        for child in root: # get settings from xml root
            if child.tag == 'Cities':
                for city in child:
                    self.cities.append(city.text)
            if child.tag == 'HasPic':
                self.hasPic = child.text
            if child.tag == 'MinPrice':
                self.minPrice = child.text
            if child.tag == 'MaxPrice':
                self.maxPrice = child.text
            if child.tag == 'CarModels':
                for car in child:
                    self.cars.append(car.text)
            if child.tag == 'MinYear':
                self.minYear = child.text
            if child.tag == 'MaxYear':
                self.maxYear = child.text
            if child.tag == 'MinMiles':
                self.minMiles = child.text
            if child.tag == 'MaxMiles':
                self.maxMiles = child.text
            if child.tag == 'TitleStatus':
                self.titleStatus = int(child.text)
            if child.tag == 'Receiver':
                self.recipientEmail = child.text
            if child.tag == 'Sender':
                self.senderEmail = child.text
            if child.tag == 'SenderPwd':
                self.senderPwd = child.text
            if child.tag == 'Blacklist':
                for keyword in child:
                    self.blacklist.append(keyword.text)

        self.LoadViewedListings() # load any previous viewed listings
        self.CreateUrls() # create the urls that the bot will search for

    def LoadViewedListings(self):
        """
        Load already viewed listings from 'viewedListings.txt'
        """
        try:
            with open('viewedListings.txt') as listings:
                for line in listings:
                    if (line == '\n' or line == '\r\n' or line == ''): # Ignore garbage lines
                        continue
                    line = line.strip()
                    self.viewedListings.append(line)
        except Exception as e:
            print("Failed to load viewed listings: {}".format(e))
                
    def SaveViewedListings(self):
        """
        Save listings to 'viewedListings.txt'
        """
        try:
            with open('viewedListings.txt', 'w') as listings:
                # reverse list to save the most recent posts
                for item in reversed(self.viewedListings):
                    listings.write("{}\n".format(item))
        except Exception as e:
            print("Failed to save viewed listings: {}".format(e))

    def CreateUrls(self):
        """
        Create the craigslist URL for each city and each car
        that is defined in the settings xml file.
        """
        for city in self.cities:
            for car in self.cars:
                url = self.BuildUrl(city, car)
                self.urlsToSearch.append(url)

    def BuildUrl(self, cityName, carModel):
        """
        Builds a string representing a craigslist url with
        the defined settings.
        returns the url string.
        """
        sUrl = "https://" + cityName + ".craigslist.org/search/cta?"
        sUrl = sUrl + "postedToday=1" # this bot only checks for listings posted the day of
        sUrl = sUrl + "&searchNearby=0" # exclude nearby results from the main results
        sUrl = sUrl + "&auto_make_model=" + carModel

        # Any settings set to None will be excluded in url
        if self.hasPic != None:
            sUrl = sUrl + "&hasPic=" + self.hasPic
        if self.minPrice != None:
            sUrl = sUrl + "&min_price=" + self.minPrice
        if self.maxPrice != None:
            sUrl = sUrl + "&max_price=" + self.maxPrice
        if self.minYear != None:
            sUrl = sUrl + "&min_auto_year=" + self.minYear
        if self.maxYear != None:
            sUrl = sUrl + "&max_auto_year=" + self.maxYear
        if self.minMiles != None:
            sUrl = sUrl + "&min_auto_miles=" + self.minMiles
        if self.maxMiles != None:
            sUrl = sUrl + "&max_auto_miles=" + self.maxMiles
        if self.titleStatus != None:
            sUrl = sUrl + "&auto_title_status=" + str(self.titleStatus)
        
        return sUrl

    def HasBlacklistedWords(self, sentence):
        """
        Checks if the sentence contains any blacklisted words.
        returns bool.
        """
        for word in self.urlsToSearch:
            if word in sentence.lower():
                return True
        return False


# Define global vars
carColors = dict()
collectedLinks = dict() # Posts for the current day
    
def SendEmail(settings_obj):
    """
    Build the body of an email with the collected links
    and send it to recipient defined in settings_obj.
    settings_obj is a Craigsettings class object 
    """
    # me == bots email address
    # you == recipient's email address
    me = settings_obj.senderEmail
    you = settings_obj.recipientEmail
    titleStatuses = {1: 'clean', 2:'salvage', 3:'rebuilt'
                    , 4:'parts only', 5:'lien', 6:'missing'}

    # Create message container - the correct MIME type is multipart/alternative.
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Craigslist Listings For the Day"
    msg['From'] = me
    msg['To'] = you
    
    # Create the body of the message (a plain-text and an HTML version).
    html = """\
    <html>
      <head></head>
      <body>
        <p>Hello I'm Craig the Craigslist Scraper Bot!<br>
               Here are the craigslists listings for today based off the specified criteria*:<br>
           <ul>
           <li><b>Cities: </b> """ +  ', '.join(settings_obj.cities) + """</li>
           <li><b>Cars: </b> """ +  ', '.join(settings_obj.cars) + """</li>
           <li><b>Minimum Price: </b> $""" + str(settings_obj.minPrice) + """</li>
           <li><b>Maximum Price: </b> $""" + str(settings_obj.maxPrice) + """</li>
           <li><b>Minimum Year: </b> """ + str(settings_obj.minYear) + """</li>
           <li><b>Maximum Mileage: </b> """ + str(settings_obj.maxMiles) + """ miles</li>
           <li><b>Title Status: </b>""" + titleStatuses[settings_obj.titleStatus] +  """</li>
           </ul>
           <br><br>
           """

    d = dict() # list of car titles already added to html list
    for car in settings_obj.cars: # order listings by car models
        html_save = html # copy of html if have to rollback due to no listings found for the car model
        no_links = True
        html = html + """<br><font size = "10px"><u><b>""" + str(car[0] + car[1:]) + "</b></u></font><br>"
        
        for key, value in collectedLinks.items():
            if (car in key.lower()):
                if carColors[value] == 'white': # provide a black bg for any white cars
                    style="color:white;background: black;"
                else:
                    style="color:{};".format(carColors[value])
                html = html + """<font size = "5px"><a href=""" + "\"" + value + "\" style=\"" + style + "\">" + key + "</a></font><br><br>"
                d[key] = value
                no_links = False
                
        # Remvoe car header if no results found for car
        if (no_links == True):
            html = html_save
    
    # Print rest of cars if the correct car category could not be found
    if (len(d) < len(collectedLinks)):
        html = html + """<font size = "5px"><u><b>Other</b></u></font><br>"""
        
        for key, value in collectedLinks.items():
            if (key not in d.keys()):
                if carColors[value] == 'white': # provide a black bg for any white cars
                    style="color:white;background: black;"
                else:
                    style="color:{};".format(carColors[value])

                html = html + """<font size="5px"><a href=""" + "\"" + value + "\" style=\"" + style + "\">" + key + "</a></font><br><br>"

    html = html + """</p>
        <p><font size="2">
        * Link color represents car color. If no color can be determined then link color defaults to orange.<br>
        * All listings are from today ( """ + datetime.datetime.now().strftime("%m/%d/%y") + """ )
        </font></p>
        </body>
    </html>
    """
    
    # Record the MIME types of both parts - text/plain and text/html.
    body = MIMEText(html, 'html')
    
    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(body)
    # msg.attach(part2)
    # Send the message via local SMTP server.
    mail = smtplib.SMTP('smtp.gmail.com', 587)
    mail.ehlo()
    mail.starttls()
    
    debug("logging in...")
    mail.login(settings_obj.senderEmail, settings_obj.senderPwd)
    debug("sending email...")
    mail.sendmail(me, you, msg.as_string().encode('utf-8'))
    mail.quit()


if __name__ == "__main__":
    sendTime = datetime.time(19, 00) # Time to send email
    bConnecting = True # bool used to break out of the connecting loop
    maxLimit = 75 # Max limit of postings to be saved to viewedListings.txt
    craig = CraigSettings("settings.cfg")
 
    # Create the urls for each city/car
    debug(craig.urlsToSearch)
    debug('------')
    debug(craig.blacklist)

    # MAIN LOOP
    while(True):
        debug("LOOPED. EMAIL TO BE SENT TO " + craig.recipientEmail + " AT " + sendTime.strftime('%I:%M:%S'))
        debug(datetime.datetime.now().time())
        time.sleep(15)
        
        # Start Connection To Craigslist page if the time is 7 o'clock
        # if (True):
        if (sendTime.hour == datetime.datetime.now().time().hour and sendTime.minute == datetime.datetime.now().time().minute):
            debug(str(datetime.datetime.now().time()) + " matches " + str(sendTime) + ": QUERYING...")
            
            # Pull data from each url
            for url in craig.urlsToSearch:
                
                bConnecting = True
                attempts = 0 # retry 10 times or skip
                # Attempt to connect to each url, retry until successful
                while(bConnecting == True and attempts < 10):
                    try:
                        r  = requests.get(url)
                        bConnecting = False
                    except Exception as e:
                        debug("FATAL ERROR: FAILED TO CONNECT TO CRAIGSLIST... RETRYING..: " + str(e))
                        attempts += 1
                        time.sleep(60)
                
                soup = BeautifulSoup(r.text, "html.parser")
                
                for result in soup.findAll("a", {"class" : "result-title"}):

                    list_name = result.contents[0] # Skip the listing if it contains a blacklisted word
                    if craig.HasBlacklistedWords(list_name) or result.attrs['href'].find('//') == 0: # href with // is a nearby result and will be ignored
                        continue

                    fullUrl = url.split('.')[0] + '.craigslist.org' # chop off search parameters of url
                    fullUrl = fullUrl + result.attrs['href'] # append listing page url
                    debug(fullUrl)

                    if (fullUrl.lower() in craig.viewedListings): # Skip duplicate postings
                        continue

                    debug(result)
                    debug('==================================================')
                    debug('--------------------------------------------------')
                    # debug(dir(result))
                    # debug(result.attrs)
                    # input('waiting for input...')

                    # Get color of car (for funsies)
                    try:
                        page = requests.get(fullUrl)
                        data = scrape_html(page.text)
                        debug(str(data.attrs['paint color']))
                        carColors[fullUrl] = data.attrs['paint color']
                    except:
                        debug("FAILED TO GET CAR COLOR. DEFAULT TO ORANGE")
                        carColors[fullUrl] = 'orange'
                                
                    collectedLinks[list_name] = fullUrl # add post to found links
                    craig.viewedListings.append(fullUrl.lower()) # add post to already viewed listings
                debug('...\n')
            
            
            debug('# of links to be emailed: ' + str(len(collectedLinks)))
            bConnecting = True
            while (bConnecting and len(collectedLinks) > 0):
                try:
                    SendEmail(craig)
                    bConnecting = False
                except Exception as e:
                    debug(str(e))
                    debug("FAILED TO SEND EMAIL... RETRYING..")
                    time.sleep(5)
                
            debug("*** FINISHED SENDING EMAIL ***")
            
            craig.viewedListings = craig.viewedListings[-maxLimit:] # Truncate viewed listings to max limit
            craig.SaveViewedListings()
                
            debug("FINISHED SAVING LISTINGS TO FILE...")
            
            # debug(collectedLinks)
            collectedLinks = dict()
            carColors = dict()
            time.sleep(60)

