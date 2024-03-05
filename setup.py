from setuptools import setup, find_packages

setup(
    name='mhtml_to_pdf_converter',
    version='0.1',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'mhtml-to-pdf=mhtml_to_pdf.converter:main',
        ],
    },
    install_requires=[
        'pdfkit',
        'beautifulsoup4',
        # 其他依赖项...
    ],
    author='Regan He',
    author_email='regan.he@outlook.com',
    description='A utility to convert MHTML files to PDF.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/Regan-He/gbt-mhtml2pdf',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
