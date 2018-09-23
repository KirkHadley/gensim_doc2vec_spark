from gensim.models.word2vec import Word2Vec
from gensim.models.doc2vec import TaggedDocument

from pyspark import SparkContext, SparkConf
from pyspark.sql import SQLContext

from pyspark.mllib.classification import LogisticRegressionWithLBFGS, LogisticRegressionModel
from pyspark.mllib.regression import LabeledPoint
 
import numpy as np
import re
from gensim_doc2vec_spark.ddoc2vecf import DistDoc2VecFast

def swap_kv(tp):
    return (tp[1], tp[0])
# parsing text
contractions = re.compile(r"'|-|\"")
# all non alphanumeric
symbols = re.compile(r'(\W+)', re.U)
# single character removal
singles = re.compile(r'(\s\S\s)', re.I|re.U)
# separators (any whitespace)
seps = re.compile(r'\s+')

def clean(text): 
    text = text.lower()
    text = contractions.sub('', text)
    text = symbols.sub(r' \1 ', text)
    text = singles.sub(' ', text)
    text = seps.sub(' ', text)
    return text

alteos = re.compile(r'([!\?])')
def make_sentences(l):
    l = alteos.sub(r' \1 .', l).rstrip("(\.)*\n")
    e = l.split(".")
    return e[0]

def parse_sentences(rdd):
    raw = rdd.zipWithIndex().map(swap_kv)
    data = raw.map(lambda text: make_sentences(text[1]))
    data = data.map(lambda x: clean(x)).zipWithIndex()
    return data

def parse_paragraphs(rdd):
    raw = rdd.zipWithIndex().map(swap_kv)

    def clean_paragraph(text):
        paragraph = []
        for s in make_sentences(text):
            paragraph = paragraph + clean(s).split()

        return paragraph

    data = raw.map(lambda text: TaggedDocument(words=clean_paragraph(text[1]), tags=text[0])) 
    return data

def word2vec(rdd):
    sentences = parse_sentences(rdd)
    sentences_without_id = sentences.map(lambda x:x[0])
    model = Word2Vec(size=100, hs=0, negative=8)
    dd2v = DistDoc2VecFast(model, learn_hidden=True, num_partitions=15, num_iterations=20)
    dd2v.build_vocab_from_rdd(sentences_without_id)
    print("*** done training words ****")
    print("*** len(model.vocab): %d ****" % len(model.vocab))
    return dd2v, sentences

def doc2vec(dd2v, rdd):
    paragraphs = parse_paragraphs(rdd)    
    dd2v.train_sentences_cbow(paragraphs)
    print("**** Done Training Doc2Vec ****")
    def split_vec(iterable):
        dvecs = iter(iterable).next()
        dvecs = dvecs['doctag_syn0']
        n = np.shape(dvecs)[0]
        return (dvecs[i] for i in xrange(n))
    return dd2v, dd2v.doctag_syn0.mapPartitions(split_vec) 

def regression(reg_data):
    (trainingData, testData) = reg_data.randomSplit([0.7, 0.3])
    lrmodel = LogisticRegressionWithLBFGS.train(trainingData)
    labelsAndPreds = testData.map(lambda p: (p.label, lrmodel.predict(p.features)))

    trainErr = labelsAndPreds.filter(lambda v, p: v != p).count() / float(testData.count())
    falsePos = labelsAndPreds.filter(lambda v, p: v != p and v == 0.0).count() / float(testData.filter(lambda lp: lp.label == 0.0).count())
    falseNeg = labelsAndPreds.filter(lambda v, p: v != p and v == 1.0).count() / float(testData.filter(lambda lp: lp.label == 1.0).count())

    print("*** Error Rate: %f ***" % trainErr)
    print("*** False Positive Rate: %f ***" % falsePos)
    print("*** False Negative Rate: %f ***" % falseNeg)

if __name__ == "__main__":
    conf = (SparkConf() \
        .set("spark.driver.maxResultSize", "4g"))

    sc = SparkContext(conf=conf)
    # sqlContext = SQLContext(sc)
    pos = sc.textFile("hdfs:///movie_review/positive")
    neg = sc.textFile("hdfs:///movie_review/negative")
    both = pos + neg

    dd2v, _ = word2vec(both)
    dd2v, docvecs = doc2vec(dd2v, both)

    dd2v.model.save("/root/doc2vec/word2vec_model/review")

    npos = pos.count()
    reg_data = docvecs.zipWithIndex().map(lambda (v, i): LabeledPoint(1.0 if i<npos else 0.0, v))
    regression(reg_data)

    
