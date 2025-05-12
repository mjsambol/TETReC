# TETReC (Tamtzit)

TETReC is a Text Editing, Translation and Review Collaboration tool, originally built for the Tamtzit HaHadashot
Israel News In Brief initiative. Tamtzit is a project of the Lokhim Akhrayut non-profit organization. This software
was developed as a voluntary contribution to help the project efficiently coordinate the efforts of a distributed team
of multilingual writers, translators and editors.

Think of TETReC as something like Google Docs, with templating, automatic translation between languages, and a simple workflow that enables a team to coordinate and efficiently assemble and publish a pure-text newsletter.

TETReC was initially deployed in late 2023 and has been in daily use by the Tamtzit team since then. Together with WhatsApp, it is the primary tool used to coordinate, produce and publish Tamtzit HaHadashot and all its translations.

## Features
 
TETReC provides a web interface through which news curators can assemble a thrice-daily news bulletin, with structure and boilerplate text provided by an underlying templating system.

A workflow coordinates transitioning the news bulletins from drafting stage to review / editing, translation, and publication.

Auto-Translation is provided based on Google Translate and OpenAI integrations. Human translators review and fine-tune
the machine-generated translation, and reviewers proof-read the results.

All work is via a simple web front-end which is suitable for use on desktop and mobile interfaces.

The tool includes an authentication mechanism which uses email and unique links rather than passwords to confirm identity, and long-lived sessions to minimize the freqency of authentication.

## Technology
TETReC is a python application which can be easily deployed to Google Cloud, or with some work, to another cloud PaaS. The original Tamtzit deployment runs on Google Cloud's AppEngine, but it can equally easily be deployed to other "serverless" infrastructure or a simple VM.

As the auto-translation component interacts with OpenAI, and OpenAI's responses could at times take long enough to cause AppEngine to time out, the translation integration can be run as a separate component in an environment where long-running responses are not a problem - such as Google Cloud Run or, again, a standard VM.

All state is stored in Google Cloud Datastore. Deploying TETReC to an environment other than Google Cloud will require non-trivial modification of the code which manages persisted data.

Other Google-specific functionality includes reliance on the Cloud Scheduler to run cron jobs.

## Limitations
TETReC was purpose-built for a specific project. It is not a general purpose editing or translation tool, though professional translators who have used it have found it superior to other software they had previously used for similar purposes. 

TETReC was written 100% by a single volunteer with a demanding full-time job completely unrelated to this project. As a result it has rough edges!

## Contact
For questions and comments please raise an issue in github.

## License
TETReC is licensed under the GNU Affero General Public License.