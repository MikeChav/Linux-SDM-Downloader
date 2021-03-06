#! /usr/bin/env python
# coding:utf-8

# first inspiration: http://v3l0c1r4pt0r.tk/2014/06/01/how-to-download-from-dreamspark-bypassing-secure-download-manager/

__author__ = 'gulliver - Radek Simkanič'
__version__ = "1.1.0"

import urllib2
import sys
import os
import shutil
import HTMLParser

from urlparse import urlparse
from subprocess import call, check_output, PIPE

import lxml
from lxml import etree

# constants
INFORMATION = 0
WARNING = 1
ERROR = 2
EXCEPTION = 3
DONE = 4

def main() :
    argv = sys.argv
    if len(argv) < 2:
        message("SDX file is not included", ERROR)
        return 1
    d = Downloader()
    d.setSdx(argv[1])
    d.execute()

def message(text, type):
    if type == INFORMATION:
        print("Info: %s" % text)
    elif type == WARNING:
        print("\033[33mWarning:\033[0m %s" % text)
    elif type == ERROR:
        print("\033[31;1mError:\033[0m %s" % text)
    elif type == EXCEPTION:
        print("\033[41;1mEXCEPTION:\033[0m %s" % text)
    elif type == DONE:
        print("\033[32;1m %s \033[0m" % text)


def findInsensitive(lxmlElement, tag, attribute, value):
    return lxmlElement.xpath("//%s[re:test(@%s, '^%s$', 'i')]"%(tag, attribute, value), namespaces={"re": "http://exslt.org/regular-expressions"})

class Downloader:
    def __init__(self):
        self._sdxFile = ""
        self._html = ""
        self._selected = 0
        self._domain = ""
        self._downloadedFiles = []
        self._parsers = []
        self._lastFileId = 0
        self._filesMapper = []
        self._glueNeeded = True


    def setSdx(self, file):
        self._sdxFile = str(file)

    def execute(self):
        if self._downloadMainPage() == False:
            return False

        if self._separateGroups() == False:
            return False

        self._getList()

        if self._downloadFiles() == False:
            return False

        self._glue()
        message("SDC file is DONE!", DONE)
        return True


    def _downloadMainPage(self):
        try:
            message("Opening SDX file", INFORMATION)
            file = open(self._sdxFile, 'r')
            url = file.readline()

            message("Parsing URL", INFORMATION)
            urlFragments = urlparse(url)
            if hasattr(urlFragments, 'netloc'):
                self._domain = urlFragments.netloc
            else:
                message("Bad URL", ERROR)
                return False

            message("Downloading main page", INFORMATION)
            response = urllib2.urlopen(url)
            html = response.read()

            self._html = html
            return True
        except ValueError:
            message(ValueError, EXCEPTION)
            return False

    def _getList(self):
        print("Choose file:")

        if self._lastFileId == 1:
            self._selected = 1
            return

        for group in self._parsers:
            group.printGroupList()

        position = input("Please select file via number 1 - %i: " % (self._lastFileId))
        position = int(position)

        if position < 1 or position > self._lastFileId:
            message("Bad choose!", WARNING)
            self._getList()
            return

        self._selected = position

    def _separateGroups(self):
        parse = etree.HTML(self._html)
        groups = parse.xpath("//div[@class='OrderItemDetails']")

        if len(groups) == 0:
            message("No groups of files", ERROR)
            return False

        groupId = 1
        fileId = 1
        for group in groups:
            parser = Parser(group, groupId, fileId)
            self._parsers.append(parser)
            fileId = parser.getLastFileId() + 1
            groupId += 1
            self._filesMapper.append(
                parser.getListFilesIds()
            )

        self._lastFileId = fileId - 1

        return True

    def _getSelectedParser(self):
        for parser in self._parsers:
            if self._selected in parser.getListFilesIds():
                return parser

    def _downloadFiles(self):
        message("Creating URL", INFORMATION)
        parser = self._getSelectedParser()
        url = parser.getDownloadUrl(
            self._selected,
            self._domain
        )
        message("Downloading page contains download link", INFORMATION)
        response = urllib2.urlopen(url)
        html = response.read()

        message("Parsing page", INFORMATION)
        parse = etree.XML(html)

        root = str(parse.tag).lower()

        if root == "AccessGuaranteeExpiry".lower():
            message("File access expiry: %s" % parse.text, ERROR)
            return False

        fileUrl = parse.xpath(".//fileUrl")
        if len(fileUrl) == 0:
            fileUrl = parse.xpath(".//fileurl")

        edv = parse.xpath(".//edv")

        if len(fileUrl) == 0:
            message("The page does not have a download link. ", ERROR)
            return False
        fileUrl = fileUrl[0].text

        if len(edv) == 0:
            message("The page does not have 'edv' key", ERROR)
            return False
        edv = edv[0].text

        name = parser.getFileName(self._selected)
        fileKeyName = "%s.key" % name

        if html.find("<edv/>") != -1:
            message("The .key file is not necessary.", INFORMATION)
        else:
            message("Creating .key file", INFORMATION)

            f = open(fileKeyName, 'w')
            f.write(edv)
            f.close()
            message("Created", DONE)

        downloadUrl = fileUrl

        # contains html entities
        if downloadUrl.find("&amp") >= 0:
            downloadUrl = HTMLParser.HTMLParser().unescape(downloadUrl)

        listUrl = downloadUrl.split('.')

        items = len(listUrl)
        iterationPosition = items - 2

        if items < 5 and len(listUrl[iterationPosition]) == 0:
            message("URL is wrong. Actual URL is: %s" % fileUrl, ERROR)
            return False

        i = 1
        while(True):
            part = str(i)
            if i < 10:
                part = "0%i" % i

            listUrl[iterationPosition] = part
            fileName = "%s.part%s" % (name, part)
            url = ".".join(listUrl)
            if self._downloadFile(url, fileName) == False:
                break
            i += 1
        if i == 1:
            self._glueNeeded = False
            if self._downloadFile(downloadUrl, name) == False:
                message("Something is wrong, probably URL", ERROR)
                return False

        message("Downloaded.", INFORMATION)
        return True

    def _downloadFile(self, url, fileName):
        
        if call("type wget" , shell=True, stdout=PIPE, stderr=PIPE) == 0:
            status = call(['wget', url])
            if status != 0:
                return False  
        
        else:
            message("Testing download URL: %s" % url, INFORMATION)
            
            request = urllib2.Request(url)
            try:
                u = urllib2.urlopen(request)
            except urllib2.URLError, e:
                return False
            meta = u.info()

            fileSize = int(meta.getheaders("Content-Length")[0])
            
            cmd = 'df -k %s' % os.getcwd()
            freeSpace = int(check_output(cmd.strip().split()).split('\n')[1].split()[3])
            diffSize = float( (fileSize - freeSpace)/ 1024.0 )
            if  freeSpace < fileSize:
                ans = raw_input("You need an additional %f MB on this drive to download the whole file, continue? (y/n) " % diffSize).strip()
            
            while ans != 'y' and ans != 'n':
                ans = raw_input("Enter y or n: ")
                if ans == 'n':
                    sys.exit()
            
            print("Downloading: %s Bytes: %s" % (fileName, fileSize) )
            
            f = open(fileName, 'wb')
            fileSizeDl = 0
            blockSize = 8192
            while True:
                buffer = u.read(blockSize)
                if not buffer:
                    break

                fileSizeDl += len(buffer)
                f.write(buffer)
                status = r"%10d  [%3.2f%%]" % (fileSizeDl, fileSizeDl * 100. / fileSize)
                status = status + chr(8)*(len(status)+1)
                print status,

            f.close()
            
            
        self._downloadedFiles.append(fileName)

        return True

    def _glue(self):
        if self._glueNeeded == False:
            message("Glue is not need", INFORMATION)
            return
        else:
            message("Gluing...", INFORMATION)
        parser = self._getSelectedParser()
        fileName = parser.getFileName(self._selected)
        if len(self._downloadedFiles) == 1:
            os.rename(self._downloadedFiles[0], fileName[self._selected])
            return

        destination = open(fileName, 'wb')
        for file in self._downloadedFiles:
            shutil.copyfileobj(open(file, 'rb'), destination)
            os.remove(file)
        destination.close()

class Parser:
    def __init__(self, etreeElementGroup, groupId, startingFileId):
        self._etreeElement = etreeElementGroup
        self._groupId = int(groupId)
        self._beginFileId = int(startingFileId)
        self._endFileId = int(startingFileId)
        self._groupName = ""
        self._dlSelect = ""
        self._oiop = []
        self._oiopu = []
        self._fileId = []
        self._fileName = []
        #self._fileUrl = []
        self._parse()

    def _parse(self):
        groupName = findInsensitive(self._etreeElement, "input", "id", "offeringNameForRequest%i"%self._groupId)
        self._groupName = groupName[0].get('value')

        # dlSelect code
        dlSelect = findInsensitive(self._etreeElement, "input", "id", "dlSelect%i"%self._groupId)
        if len(dlSelect) == 0:
                message("#dlSelect%d is not found"%self._groupId, ERROR)
                return False
        dlSelect = dlSelect[0]
        self._dlSelect = dlSelect.get('value')

        # other data
        edvCounter = 0
        edv = findInsensitive(self._etreeElement, "input", "id", "edv")

        if len(edv) == 0:
            i = self._endFileId
            while(True):
                edv = findInsensitive(self._etreeElement, "input", "id", "edv%i"%self._groupId)

                if len(edv) == 0:

                    edvCounter = self._groupId-1
                    self._endFileId = edvCounter
                    break

                oiop = findInsensitive(self._etreeElement, "input", "id", "oiop%i"%self._groupId)
                oiopu = findInsensitive(self._etreeElement, "input", "id", "oiopu%i"%self._groupId)
                fileId = findInsensitive(self._etreeElement, "input", "id", "fileId%i"%self._groupId)
                fileName = findInsensitive(self._etreeElement, "input", "id", "fileName%i"%self._groupId)
                #fileUrl = findInsensitive(self._etreeElement, "input", "id", "fileUrl%i"%self._groupId)

                if len(oiop) == 0 or len(oiopu) == 0 or len(fileId) == 0 or len(fileName) == 0:
                    message("Fragments is not found during parsing", ERROR)
                    return False
                oiop = oiop[0].get("value")
                oiopu = oiopu[0].get("value")
                fileId = fileId[0].get("value")
                fileName = fileName[0].get("value")
                #fileUrl = fileUrl[0]

                self._oiop.append(
                    oiop
                )
                self._oiopu.append(
                    oiopu
                )
                self._fileId.append(
                    fileId
                )
                self._fileName.append(
                    fileName
                )
                #self._fileUrl.append(
                #    fileUrl.tostring(fileUrl)
                #)

                self._groupId += 1
        else:
            message("Edv is only one", INFORMATION)
            edvCounter = 1

        if edvCounter == 0:
            message("Edv is not found", ERROR)
            return False

        message("Parsing done!", INFORMATION)

    def printGroupList(self):
        print("\t%s"%self._groupName)

        i = self._beginFileId
        for name in self._fileName:
            print("\t#%i | %s" % (i, name))
            i += 1

    def getLastFileId(self):
        return self._endFileId

    def getListFilesIds(self):
        return xrange(self._beginFileId, self._endFileId + 1)

    def getDownloadUrl(self, selected, domain):
        position = selected - self._beginFileId
        url = "http://%s/WebStore/Account/SDMAuthorize.ashx?oiopu=%s&f=%s&oiop=%s&dl=%s" \
              % (domain, self._oiopu[position], self._fileId[position], self._oiop[position], self._dlSelect)

        return url

    def getFileName(self, fileId):
        position = fileId - self._beginFileId
        return self._fileName[position]

if __name__ == '__main__':
    main()

