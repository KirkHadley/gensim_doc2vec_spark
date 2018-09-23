from setuptools import setup, find_packages

setup(name='gensim_doc2vec_spark',
      version='0.1',
      description='doc2vec for spark',
      author='Yiran Sheng',
      url='https://github.com/KirkHadley/gensim_doc2vec_spark',
      packages=find_packages(),
      install_requires = [
          'gensim'
          ]
     )
