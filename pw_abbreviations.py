# -*- coding: utf-8 -*-

from PyQt5.QtCore import QCoreApplication
from qgis.utils import iface
#from osgeo import gdal
import os
import sys
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterField,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum,
                       QgsFeatureRequest,
                       QgsSpatialIndex,
                       QgsGeometry,
                       QgsRectangle,
                       QgsPointXY,
                       )
import processing

class ExampleProcessingAlgorithm(QgsProcessingAlgorithm):
    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    INPUT = 'INPUT'
    INPUT_MATRIX = 'INPUT MATRIX'
    FIELD = 'FIELD'
    OUTPUT_FIELD = 'OUTPUT FIELD'
    RESOLVE_CASE = 'RESOLVE CASE'
    RESOLVE_FIRST = 'RESOLVE FIRST'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ExampleProcessingAlgorithm()

    def name(self):
        return 'pw_abbreviations'

    def displayName(self):
        return self.tr('PW ABBREVIATIONS')

    def group(self):
        return self.tr('PW')

    def groupId(self):
        return 'pw'

    def shortHelpString(self):
        help = """This algorithm expands abbreviations from input features; if text is recognized as abbreviation, the algorithm replaces it by last previous word in the text (in reading order).\
        Additionally it changes first letters in the words to capitals and the others to lower. If words in the text are sorted in alphabetical order, the algorithm can recognize words with first letter not matching to its neighborhood and change it to proper letter.\
        <hr>
        <b>Input abbreviations layer</b>\
        <br>The features contain abbreviations to expand.\
        <br><br><b>Input sheets layer</b>\
        <br>The features with extands of sheets.\
        <br><br><b>Text input field</b>\
        <br>The field in the input table contains abbreviations to expand.\
        <br><br><b>Text output field</b>\
        <br>The field in the input table in which the expanded abbreviations will be add.\
        <br><br><b>Characters to remove on edges</b>\
        <br>If input text starts or ends with character from the list, this character will be remove from text.\
        <br><br><b>Resolve first</b>\
        <br>Changes first letters in the words to capitals and the others to lower letters.\
        <br><br><b>Resolve capitalization</b>\
        <br>Recognizes words with first letter not matching to its neighborhood and changes it to proper letter.\
        (Alphabetical order of text words is necassery)\
        <br><br><b>Output layer</b>\
        <br>Location of the output layer.\
        """
        return self.tr(help)

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input abbreviations layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_MATRIX,
                self.tr('Input sheets layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD,
                self.tr('Text input field'),
                parentLayerParameterName = self.INPUT,
                type = QgsProcessingParameterField.DataType.String
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.OUTPUT_FIELD,
                self.tr('Text output field'),
                parentLayerParameterName = self.INPUT,
                type = QgsProcessingParameterField.DataType.String
            )
        )
        global CharsList
        CharsList = ['.',',',':',';','/','\\','"',"'",'|','_','*','!','^','~','+','@','#','$','&','(',')',' ','0','1','2','3','4','5','6','7','8','9']
        global Checklist
        Checklist = []
        for i in range(0,len(CharsList),1):
            Checklist.append(i)
        
        self.addParameter(
            QgsProcessingParameterEnum(
                'LIST',
                self.tr('Characters to remove on edges'),
                options = CharsList,
                allowMultiple = True,
                defaultValue = Checklist,
                optional = True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RESOLVE_FIRST,
                self.tr('Resolve first')
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RESOLVE_CASE,
                self.tr('Resolve capitalization')
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output layer')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        self.source_layer = self.parameterAsLayer(
            parameters,
            self.INPUT,
            context
        )
        self.feature_source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )
        self.field = self.parameterAsString(
            parameters,
            self.FIELD,
            context
        )
        self.dest_field = self.parameterAsString(
            parameters,
            self.OUTPUT_FIELD,
            context
        )
        self.matrix_feature_source = self.parameterAsSource(
            parameters,
            self.INPUT_MATRIX,
            context
        )
        self.chars_indices = self.parameterAsEnums(
            parameters,
            'LIST',
            context
        )
        self.case = self.parameterAsBool(
            parameters,
            self.RESOLVE_CASE,
            context
        )
        self.first = self.parameterAsBool(
            parameters,
            self.RESOLVE_FIRST,
            context
        )
        (self.sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            self.feature_source.fields(),
            self.feature_source.wkbType(),
            self.feature_source.sourceCrs()
        )
        feedback.setProgressText('\nsorting sheets in reading order...\n')
        matrix_features_iterator = self.matrix_feature_source.getFeatures(QgsFeatureRequest())
        matrix_features = []
        for feat in matrix_features_iterator:
            matrix_features.append(feat)
        SheetsOrderedList = self.PutInOrderFeatures(feedback, matrix_features)
        
        features_iterator = self.feature_source.getFeatures(QgsFeatureRequest())
        self.index = QgsSpatialIndex()
        for feat in features_iterator:
            self.index.insertFeature(feat)
        feedback.setProgressText('\nsorting features in reading order...\n')
        OrderedFeatures = []
        for sheet in SheetsOrderedList:
            if feedback.isCanceled(): break
            FirstColumnRect = self.TakeColumnRect(feedback,sheet)[0]
            SecondColumnRect = self.TakeColumnRect(feedback,sheet)[1]
            FeaturesInFirstColumn = self.index.intersects(FirstColumnRect)
            FeaturesInSecondColumn = self.index.intersects(SecondColumnRect)
            self.RemoveWrongIds(feedback, FirstColumnRect, FeaturesInFirstColumn)
            self.RemoveWrongIds(feedback, SecondColumnRect, FeaturesInSecondColumn)
            if len(FeaturesInFirstColumn)>0: OrderedFeatures = OrderedFeatures + self.PutInOrderFeatures(feedback, self.IdsListToFeaturesList(feedback, FeaturesInFirstColumn))
            if len(FeaturesInSecondColumn)>0: OrderedFeatures = OrderedFeatures + self.PutInOrderFeatures(feedback, self.IdsListToFeaturesList(feedback, FeaturesInSecondColumn))
        global CharsList
        self.CharsToRemove = [CharsList[index] for index in self.chars_indices]
        feedback.pushCommandInfo('Characters to remove: ' + str(self.CharsToRemove))
        feedback.setProgressText('\nprocessing time calculating...\n')
        self.total = len(OrderedFeatures)
        self.actual = 0
        if self.total>0: feedback.setProgress(self.actual/self.total*100)
        if OrderedFeatures: lastlong = str(OrderedFeatures[0][self.field])
        for feat in OrderedFeatures:
            if feedback.isCanceled(): break
            lp = OrderedFeatures.index(feat)
            string = str(feat[self.field])
            feedback.pushCommandInfo('old: '+string)
            string = self.OnEachFeatureChars(feedback, string)

            if self.if_short(string, 3):
                string = lastlong
            else:
                if self.first: string = self.OnEachFeatureResolveFirst(feedback, string, feat, OrderedFeatures)
                if self.case: string = self.OnEachFeatureCaseSens(feedback, string)
                lastlong = string
            feedback.pushCommandInfo('new: '+string)
            self.actual = self.actual + 1
            feedback.setProgress(self.actual/self.total*100)
            feedback.setProgressText(str(self.actual)+'/'+str(self.total) + '       ' +'id:  ' + str(feat.id()))
            feat[self.dest_field] = string
            self.sink.addFeature(feat, QgsFeatureSink.FastInsert)
        return {'Resolved features': self.actual}
    def if_short(self, string, minimum):
        bool = True
        for part in string.split():
            if len(part)>minimum:
                bool = False
        if string == 'NULL': bool = True
        return bool
    def most_frequent(self, List): 
        return max(set(List), key = List.count)
    def OnEachFeatureResolveFirst(self, feedback, string, feat, featlist):
        coms = False
        m = 8
        list = []
        index = featlist.index(feat)
        if coms: feedback.pushCommandInfo('index: '+str(index))
        for i in range(0,m,1):
            n = index-int(m/2)+i
            if n<0: continue
            try:
                list.append(featlist[n][self.field][0])
            except:
               continue
        if coms: feedback.pushCommandInfo('list: '+str(list))
        most = self.most_frequent(list)
        if coms: feedback.pushCommandInfo('most: '+str(most))
        prefix=''
        for i in string: 
            if (i.isupper() or i==' '):
                prefix +=i
            else:
                break
        preflen=len(prefix)
        firstmostindex = 0
        if preflen==0:
            if string[0] != most.lower():
                string = most+string[1:]
        elif preflen < len(string):
            for i in prefix:
                if i==most:
                    break
                else:
                    firstmostindex = firstmostindex+1
            if firstmostindex < preflen:
                string=string[firstmostindex:]
            else:
                if string[firstmostindex]==most.lower():
                    string=string[firstmostindex:]
                else:
                    string=most+string[firstmostindex:]

        return string
    def OnEachFeatureCaseSens(self, feedback, string):
        lista=[]
        listb=[]
        for word in string.split():
            listw = list(word)
            for i in range(0,len(listw),1):
                if i==0: word = listw[i].upper()
                else:
                    word += listw[i].lower()
            lista.append(word)
        string = ' '.join(lista)
        for word in string.split("-"):
            listw = list(word)
            for i in range(0,len(listw),1):
                if i==0: word = word[0].upper()
                else:
                    word += listw[i]
            listb.append(word)
        string = '-'.join(listb)
        return string
    def OnEachFeatureChars(self, feedback, string):
        coms = False
        if coms: feedback.pushCommandInfo('string:' + string)
        
        ln = len(string)
        for i in range(0,ln-1,1):
            if coms: feedback.pushCommandInfo('ln: ' + str(ln))
            if coms: feedback.pushCommandInfo('i: ' + str(i))
            if string[i] not in self.CharsToRemove:
                string = string[i:]
                break
                
        ln = len(string)
        for i in range(1,ln-1,1):
            if coms: feedback.pushCommandInfo('ln: ' + str(ln))
            if coms: feedback.pushCommandInfo('i: ' + str(i))
            j = ln-i
            if coms: feedback.pushCommandInfo('j: ' + str(j))
            if string[j] in self.CharsToRemove:
                if coms: feedback.pushCommandInfo('string[j]: ' + str(string[j]))
                string = string[:j]
                if coms: feedback.pushCommandInfo('finally string:' + string)
            else:
                break

        return string
    def IdsListToFeaturesList(self, feedback, IdsList):
        FeatList=[]
        for id in IdsList:
            FeatList.append(self.source_layer.getFeature(id))
        return FeatList
    def RemoveWrongIds(self, feedback, ColumnRect, IdsList):
        for id in IdsList:
                 if not ColumnRect.contains(self.source_layer.getFeature(id).geometry().centroid().asPoint()):
                     IdsList.remove(id)
    def TakeColumnRect(self, feedback, sheet):
        """Returns two rectangles: first and second column"""
        bbox = sheet.geometry().boundingBox()
        x1, x2, x3, y1, y2 = bbox.xMinimum(), bbox.xMinimum() + (bbox.xMaximum() - bbox.xMinimum())/2, bbox.xMaximum(), bbox.yMinimum(), bbox.yMaximum()
        FirstColumnRect = QgsRectangle(QgsPointXY(x1,y2),QgsPointXY(x2,y1))
        SecondColumnRect = QgsRectangle(QgsPointXY(x2,y2),QgsPointXY(x3,y1))
        
        return [FirstColumnRect,SecondColumnRect]
        
    def PutInOrderFeatures(self, feedback, features_list):
        """ Function puts features in reading order; from left to right in text lines. Used to arrange matrix features and text features in columns"""
        ListByX = features_list.copy()
        ListByX.sort(key = self.sortX)
        ListByY = features_list.copy()
        ListByY.sort(key = self.sortY)
        w, h = len(features_list), len(features_list)
        matrix = [[None] * w for i in range(h)]
        """This part builds 2D features positions table. Each row and column contains only one feature. Teble is inversed, beacause y canvas coord ascends up"""
        for feat in features_list:
            x = ListByX.index(feat)
            y = ListByY.index(feat)
            matrix[y][x] = feat
        """Identifying features lying in the same line; merging and deleting these rows"""
        for row in matrix:
            if matrix.index(row) < (len(matrix)-1):
                for element in matrix[matrix.index(row)+1]:
                    if element != None: y_upper = element.geometry().centroid().asPoint().y()
                for element in row:
                    if element != None:
                        if element.geometry().boundingBox().height()/2>(y_upper-element.geometry().centroid().asPoint().y()):
                            matrix[matrix.index(row)+1][row.index(element)]=element
                            row[row.index(element)] = None
        ToDelete = [None] * w
        if ToDelete in matrix: matrix.remove(ToDelete)
        """Inverting table order and rewriting features ti list ordered properly"""
        matrix.reverse()
        OrderedList =[]
        for row in matrix:
            for element in row:
                if element != None:
                    OrderedList.append(element)
        
        return OrderedList
        
    def sortX(self,feat): 
        return feat.geometry().centroid().asPoint().x()
    def sortY(self,feat): 
        return feat.geometry().centroid().asPoint().y()
