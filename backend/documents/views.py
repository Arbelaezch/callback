import os

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from callback.config import CONTEXT_UPLOAD_EXTENSIONS, CONTEXT_UPLOAD_MAX_BYTES
from pipeline.storage import delete_resume, upload_context_document
from users.models import Resume

from .models import ContextSource, GeneratedDocument, JobPosting, ParsedResume
from .rendering import html_to_pdf, render_cover_letter_html, render_resume_html
from .serializers import (
    ContextSourceSerializer,
    GeneratedDocumentSerializer,
    JobPostingSerializer,
    ParsedResumeSerializer,
)
from .services import index_upload_source
from .tasks import generate_documents_task, parse_resume_task


class ResumeParseView(APIView):
    """POST queues analysis of a ready resume; GET returns the parsed result."""
    permission_classes = [IsAuthenticated]

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
        parse_resume_task.delay(resume.pk)
        return Response({'detail': 'Parsing started.'}, status=status.HTTP_202_ACCEPTED)


class ContextSourceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
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
        posting = JobPosting.objects.filter(pk=job_id, user=request.user).first()
        if posting is None:
            return Response({'detail': 'Job posting not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(JobPostingSerializer(posting).data)


class GenerateView(APIView):
    """POST {resume_id} queues generation of a tailored resume and cover letter."""
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        posting = JobPosting.objects.filter(pk=job_id, user=request.user).first()
        if posting is None:
            return Response({'detail': 'Job posting not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            resume_id = int(request.data.get('resume_id'))
        except (TypeError, ValueError):
            return Response({'detail': 'resume_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not ParsedResume.objects.filter(resume_id=resume_id, user=request.user).exists():
            return Response(
                {'detail': 'That resume has not been parsed yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        generate_documents_task.delay(posting.pk, resume_id)
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
