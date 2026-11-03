import logging
import os

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from callback.throttles import ReadableThrottleMixin
from callback.config import (
    CONTEXT_UPLOAD_EXTENSIONS,
    CONTEXT_UPLOAD_MAX_BYTES,
    COVER_LETTER_UPLOAD_EXTENSIONS,
    COVER_LETTER_UPLOAD_MAX_BYTES,
    DAILY_GENERATION_LIMIT,
    DAILY_PARSE_LIMIT,
)
from pipeline.storage import delete_resume, upload_context_document, upload_cover_letter_sample
from users.models import CoverLetterSample, Resume

from .generation import create_pending_documents
from .limits import (
    DAILY_GENERATION_LIMIT_ERROR,
    DAILY_PARSE_LIMIT_ERROR,
    GENERATION_IN_FLIGHT_ERROR,
    PARSE_IN_FLIGHT_ERROR,
    generation_in_flight,
    generations_last_day,
    lock_user,
    parse_in_flight,
    parses_last_day,
)
from .models import ContextSource, GeneratedDocument, JobPosting, ParsedResume, ParseRequest
from .rendering import html_to_pdf, render_cover_letter_html, render_resume_html
from .serializers import (
    ContextSourceSerializer,
    GeneratedDocumentSerializer,
    JobPostingSerializer,
    ParsedResumeSerializer,
    ParsedResumeSummarySerializer,
)
from .services import index_upload_source, ingest_cover_letter_sample
from .staleness import fail_stale_documents, fail_stale_parses, fail_stale_sources
from .tasks import generate_documents_task, parse_resume_task
from .validation import validate_document_content

logger = logging.getLogger(__name__)


class ResumeParseView(ReadableThrottleMixin, APIView):
    """POST queues analysis of a ready resume; GET returns the parsed result."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'parse'

    def _resume(self, request, resume_id):
        return Resume.objects.filter(pk=resume_id, user=request.user).first()

    def get(self, request, resume_id):
        parsed = ParsedResume.objects.filter(resume_id=resume_id, user=request.user).first()
        if parsed is None:
            return Response({'detail': 'Resume has not been parsed.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ParsedResumeSerializer(parsed).data)

    def post(self, request, resume_id):
        resume = self._resume(request, resume_id)
        if resume is None:
            return Response({'detail': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)
        if resume.status != 'ready':
            return Response({'detail': 'Resume is not ready.'}, status=status.HTTP_400_BAD_REQUEST)
        fail_stale_parses(request.user)
        with transaction.atomic():
            lock_user(request.user)
            resume = Resume.objects.get(pk=resume.pk)
            if parse_in_flight(resume):
                return Response({'detail': PARSE_IN_FLIGHT_ERROR}, status=status.HTTP_409_CONFLICT)
            if parses_last_day(request.user) >= DAILY_PARSE_LIMIT:
                return Response({'detail': DAILY_PARSE_LIMIT_ERROR}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            resume.parse_status = 'pending'
            resume.parse_error = ''
            resume.parse_requested_at = timezone.now()
            resume.save(update_fields=['parse_status', 'parse_error', 'parse_requested_at'])
            ParseRequest.objects.create(user=request.user, resume=resume)
        # If queueing fails the ParseRequest row stays, so it still counts toward the daily cap.
        try:
            parse_resume_task.delay(resume.pk)
        except Exception:
            logger.exception('Could not queue parse for resume %s', resume.pk)
            detail = 'Could not start analysis. Please try again.'
            resume.parse_status = 'failed'
            resume.parse_error = detail
            resume.save(update_fields=['parse_status', 'parse_error'])
            return Response({'detail': detail}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'detail': 'Parsing started.'}, status=status.HTTP_202_ACCEPTED)


class ParsedResumeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        parsed = ParsedResume.objects.filter(user=request.user)
        return Response(ParsedResumeSummarySerializer(parsed, many=True).data)


class CoverLetterSampleView(ReadableThrottleMixin, APIView):
    """The user's default cover letter sample: the voice reference for writing.

    GET returns the ready default sample. POST uploads a .pdf or .txt, extracts its
    text in the request and makes it the default. There is no way to paste text.
    """
    permission_classes = [IsAuthenticated]
    throttle_scope = 'cover_letter_upload'

    def _sample(self, user):
        return (
            CoverLetterSample.objects.filter(user=user, status='ready')
            .order_by('-is_default', '-created_at')
            .first()
        )

    def _payload(self, sample):
        if sample is None:
            return {'body': '', 'filename': '', 'updated_at': None}
        return {
            'body': sample.body,
            'filename': sample.filename,
            'updated_at': sample.updated_at.isoformat() if sample.updated_at else None,
        }

    def get(self, request):
        return Response(self._payload(self._sample(request.user)))

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        extension = os.path.splitext(file.name)[1].lower()
        if extension not in COVER_LETTER_UPLOAD_EXTENSIONS:
            return Response(
                {'detail': f'File must be one of: {", ".join(COVER_LETTER_UPLOAD_EXTENSIONS)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > COVER_LETTER_UPLOAD_MAX_BYTES:
            return Response({'detail': 'File is too large.'}, status=status.HTTP_400_BAD_REQUEST)
        if extension == '.pdf':
            header = file.read(5)
            file.seek(0)
            if header != b'%PDF-':
                return Response({'detail': 'File is not a valid PDF.'}, status=status.HTTP_400_BAD_REQUEST)

        # Never default until ingest succeeds, so readers of is_default only see ready rows.
        sample = CoverLetterSample.objects.create(
            user=request.user, label=file.name[:100], filename=file.name[:255],
            status='pending', is_default=False,
        )
        try:
            sample.s3_key = upload_cover_letter_sample(file, request.user.id, extension)
            sample.save(update_fields=['s3_key'])
            ingest_cover_letter_sample(sample)
        except Exception:
            sample.refresh_from_db()
            if sample.error:
                return Response({'detail': sample.error}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
            if sample.status == 'pending':
                logger.exception('Cover letter sample upload failed for sample %s', sample.pk)
                sample.status = 'failed'
                sample.save(update_fields=['status', 'updated_at'])
            return Response(
                {'detail': 'Upload failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(self._payload(sample), status=status.HTTP_201_CREATED)


class ContextSourceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        fail_stale_sources(request.user)
        sources = ContextSource.objects.filter(user=request.user)
        return Response(ContextSourceSerializer(sources, many=True).data)

    def post(self, request):
        """Add a supporting document. Git and Obsidian sources are not supported yet."""
        kind = request.data.get('kind', 'upload')
        if kind != 'upload':
            return Response(
                {'detail': f'Source kind "{kind}" is not supported yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        extension = os.path.splitext(file.name)[1].lower()
        if extension not in CONTEXT_UPLOAD_EXTENSIONS:
            return Response(
                {'detail': f'File must be one of: {", ".join(CONTEXT_UPLOAD_EXTENSIONS)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > CONTEXT_UPLOAD_MAX_BYTES:
            return Response({'detail': 'File is too large.'}, status=status.HTTP_400_BAD_REQUEST)

        source = ContextSource.objects.create(
            user=request.user, kind='upload', label=request.data.get('label') or file.name,
        )
        try:
            source.s3_key = upload_context_document(file, request.user.id, extension)
            source.save(update_fields=['s3_key'])
            index_upload_source(source)
        except Exception:
            source.refresh_from_db()
            return Response(
                {'detail': source.error or 'Upload failed. Please try again.', **ContextSourceSerializer(source).data},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY if source.error else status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        source.refresh_from_db()
        return Response(ContextSourceSerializer(source).data, status=status.HTTP_201_CREATED)


class ContextSourceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, source_id):
        source = ContextSource.objects.filter(pk=source_id, user=request.user).first()
        if source is None:
            return Response({'detail': 'Source not found.'}, status=status.HTTP_404_NOT_FOUND)
        if source.s3_key:
            delete_resume(source.s3_key)
        source.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JobPostingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        fail_stale_documents(request.user)
        postings = JobPosting.objects.filter(user=request.user).prefetch_related('documents')
        return Response(JobPostingSerializer(postings, many=True).data)

    def post(self, request):
        serializer = JobPostingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class JobPostingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        fail_stale_documents(request.user)
        posting = JobPosting.objects.filter(pk=job_id, user=request.user).first()
        if posting is None:
            return Response({'detail': 'Job posting not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(JobPostingSerializer(posting).data)


NO_PRIMARY_RESUME_ERROR = 'Set a primary resume on your profile first.'
PRIMARY_NOT_PARSED_ERROR = (
    'Your primary resume has not been analyzed yet. Analyze it on your profile first.'
)
RESUME_NOT_PARSED_ERROR = 'That resume has not been parsed yet.'


class GenerateView(ReadableThrottleMixin, APIView):
    """POST {resume_id?} queues generation of a tailored resume and cover letter. Without resume_id, uses the user's primary resume."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'generate'

    def post(self, request, job_id):
        posting = JobPosting.objects.filter(pk=job_id, user=request.user).first()
        if posting is None:
            return Response({'detail': 'Job posting not found.'}, status=status.HTTP_404_NOT_FOUND)

        raw = request.data.get('resume_id')
        if raw in (None, ''):
            primary = Resume.objects.filter(user=request.user, is_default=True, status='ready').first()
            if primary is None:
                return Response({'detail': NO_PRIMARY_RESUME_ERROR}, status=status.HTTP_400_BAD_REQUEST)
            parsed = ParsedResume.objects.filter(
                resume=primary, user=request.user,
            ).select_related('resume').first()
            if parsed is None:
                return Response({'detail': PRIMARY_NOT_PARSED_ERROR}, status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                resume_id = int(raw)
            except (TypeError, ValueError):
                return Response(
                    {'detail': 'resume_id must be a number.'}, status=status.HTTP_400_BAD_REQUEST,
                )
            parsed = ParsedResume.objects.filter(
                resume_id=resume_id, user=request.user, resume__status='ready',
            ).select_related('resume').first()
            if parsed is None:
                return Response({'detail': RESUME_NOT_PARSED_ERROR}, status=status.HTTP_400_BAD_REQUEST)
        fail_stale_documents(request.user)
        with transaction.atomic():
            lock_user(request.user)
            if generation_in_flight(posting):
                return Response({'detail': GENERATION_IN_FLIGHT_ERROR}, status=status.HTTP_409_CONFLICT)
            if generations_last_day(request.user) >= DAILY_GENERATION_LIMIT:
                return Response(
                    {'detail': DAILY_GENERATION_LIMIT_ERROR}, status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            resume_doc, letter_doc = create_pending_documents(posting, parsed.resume)
        try:
            generate_documents_task.delay(resume_doc.pk, letter_doc.pk)
        except Exception:
            logger.exception('Could not queue generation for job posting %s', posting.pk)
            detail = 'Could not start generation. Please try again.'
            GeneratedDocument.objects.filter(pk__in=[resume_doc.pk, letter_doc.pk]).update(
                status='failed', error=detail, updated_at=timezone.now(),
            )
            return Response({'detail': detail}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'detail': 'Generation started.'}, status=status.HTTP_202_ACCEPTED)


class GeneratedDocumentView(APIView):
    """GET a generated document; PATCH to save the user's edits."""
    permission_classes = [IsAuthenticated]

    def _document(self, request, document_id):
        return GeneratedDocument.objects.filter(
            pk=document_id, job_posting__user=request.user,
        ).first()

    def get(self, request, document_id):
        document = self._document(request, document_id)
        if document is None:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(GeneratedDocumentSerializer(document).data)

    def patch(self, request, document_id):
        document = self._document(request, document_id)
        if document is None:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        if document.status != 'ready':
            return Response({'detail': 'Document is not ready.'}, status=status.HTTP_409_CONFLICT)
        if 'content' in request.data:
            errors = validate_document_content(document.kind, request.data['content'])
            if errors:
                return Response({'content': errors}, status=status.HTTP_400_BAD_REQUEST)
        serializer = GeneratedDocumentSerializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(edited=True)
        return Response(serializer.data)


def _document_html(document) -> str:
    if document.kind == 'resume':
        return render_resume_html(document.content, document.layout)
    return render_cover_letter_html(
        document.markdown, (document.content or {}).get('header'), document.layout,
    )


class _RenderedDocumentView(APIView):
    permission_classes = [IsAuthenticated]

    def get_ready_document(self, request, document_id):
        """Return (document, None) or (None, error Response)."""
        document = GeneratedDocument.objects.filter(
            pk=document_id, job_posting__user=request.user,
        ).first()
        if document is None:
            return None, Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        if document.status != 'ready':
            return None, Response({'detail': 'Document is not ready.'}, status=status.HTTP_409_CONFLICT)
        return document, None


class DocumentPreviewView(_RenderedDocumentView):
    """The document as HTML, for the editor's live preview."""

    def get(self, request, document_id):
        document, error = self.get_ready_document(request, document_id)
        if error:
            return error
        return HttpResponse(_document_html(document), content_type='text/html; charset=utf-8')


class DocumentExportView(_RenderedDocumentView):
    """The document as a PDF download. X-Page-Count lets the UI warn about overflow."""

    def get(self, request, document_id):
        document, error = self.get_ready_document(request, document_id)
        if error:
            return error
        pdf, pages = html_to_pdf(_document_html(document))
        name = 'resume' if document.kind == 'resume' else 'cover-letter'
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{name}.pdf"'
        response['X-Page-Count'] = str(pages)
        response['Access-Control-Expose-Headers'] = 'X-Page-Count'
        return response
