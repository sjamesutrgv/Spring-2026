# mycalendar/views.py
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from datetime import datetime, date, timedelta
from .utils import CustomCalendar
from .models import Event, Profile
from .forms import EventForm, ProfileForm
from .twitch import TwitchAPIError, hydrate_event_twitch_data, is_configured, refresh_event_live_status
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login


TOURNAMENT_ORGANIZER_GROUP = 'Tournament Organizer'


def is_tournament_organizer(user):
    return (
        user.is_authenticated
        and (
            user.is_staff
            or user.is_superuser
            or user.groups.filter(name=TOURNAMENT_ORGANIZER_GROUP).exists()
        )
    )


def show_calendar(request, year=None, month=None):
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    else:
        year = int(year)
        month = int(month)

    # Logic for Previous and Next buttons
    current_date = date(year, month, 1)
    prev_month = current_date - timedelta(days=1)
    next_month = current_date + timedelta(days=32) # Jumps to next month

    cal = CustomCalendar(year, month)
    html_calendar = cal.formatmonth(year, month)

    # --- NEW CODE STARTS HERE --- 
    # ADDING EVENT HIGHLIGHTING
    # Fetch all events for this specific month and year
    events_this_month = Event.objects.filter(date__year=year, date__month=month)
    event_days = list(events_this_month.values_list('date__day', flat=True))
    # --- NEW CODE ENDS HERE ---

    context = {
        'calendar': html_calendar,
        'year': year,
        'month': month,
        'prev_year': prev_month.year,   
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
        'event_days': event_days,  # Pass the list of event days to the template
        'can_create_events': request.user.is_authenticated,
    }
    return render(request, 'mycalendar/calendar.html', context)

# NEW VIEW: Handles the specific day's events
def daily_events(request, year, month, day):
    # Fetch all events from the database that match this exact date
    events = Event.objects.filter(date__year=year, date__month=month, date__day=day)

    if is_configured():
        for event in events:
            if event.twitch_login:
                try:
                    refresh_event_live_status(event)
                    event.save(update_fields=[
                        'twitch_live_status',
                        'twitch_stream_title',
                        'twitch_stream_game_name',
                        'twitch_viewer_count',
                        'twitch_last_checked_at',
                    ])
                except TwitchAPIError:
                    messages.warning(request, 'Twitch live status could not be refreshed right now.')
                    break
    
    # Format a nice date string for the template
    date_obj = datetime(year, month, day)
    formatted_date = date_obj.strftime('%B %d, %Y')

    context = {
        'events': events,
        'date': formatted_date,
        'date_value': date_obj.strftime('%Y-%m-%d'),
        'can_create_events': request.user.is_authenticated,
    }
    return render(request, 'mycalendar/events.html', context)


@login_required
def toggle_event_registration(request, event_id):
    if request.method != 'POST':
        return redirect('calendar-home')

    event = get_object_or_404(Event, id=event_id)

    if event.attendees.filter(id=request.user.id).exists():
        event.attendees.remove(request.user)
        messages.success(request, f'You are no longer registered for {event.title}.')
    else:
        event.attendees.add(request.user)
        messages.success(request, f'You are registered for {event.title}.')

    return redirect('daily-events', year=event.date.year, month=event.date.month, day=event.date.day)

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("calendar-home")
    else:
        form = UserCreationForm()

    return render(request, "mycalendar/signup.html", {"form": form})

#Handles the homepage and upcoming events
def home(request):
    # Get today's date
    today = date.today()
    
    # Fetch events where the date is greater than or equal to today, 
    # order them chronologically, and grab the first 5
    upcoming_events = Event.objects.filter(date__gte=today).order_by('date')[:5]
    
    context = {
        'events': upcoming_events,
        'can_create_events': request.user.is_authenticated,
    }
    return render(request, 'home.html', context)


@login_required
def my_events(request):
    registered_events = request.user.registered_events.order_by('date', 'start_time', 'title')

    context = {
        'registered_events': registered_events,
    }
    return render(request, 'mycalendar/my_events.html', context)


@login_required
def create_event(request):
    initial = {}
    requested_date = request.GET.get('date')
    if requested_date:
        initial['date'] = requested_date

    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            is_organizer = is_tournament_organizer(request.user)
            has_twitch_link = bool(form.cleaned_data.get('twitch_url'))

            if not is_organizer and not has_twitch_link:
                form.add_error(None, 'Add a Twitch link to post a stream event, or ask an admin for Tournament Organizer access.')
                return render(request, 'mycalendar/create_event.html', {'form': form})

            event = form.save(commit=False)
            event.created_by = request.user

            if event.twitch_url:
                if is_configured():
                    try:
                        hydrate_event_twitch_data(event)
                    except TwitchAPIError as error:
                        form.add_error('twitch_url', str(error))
                        return render(request, 'mycalendar/create_event.html', {'form': form})
                else:
                    messages.warning(request, 'Twitch API keys are not configured yet, so the event was saved without Twitch profile data.')

            event.save()
            messages.success(request, 'Event pinned to the calendar.')
            return redirect('daily-events', year=event.date.year, month=event.date.month, day=event.date.day)
    else:
        form = EventForm(initial=initial)

    return render(request, 'mycalendar/create_event.html', {'form': form})

# NEW VIEW: The User Profile Page
@login_required
def profile(request):
    # This safely gets the user's profile, or creates a blank one if they just signed up
    user_profile, created = Profile.objects.get_or_create(user=request.user)
    
    return render(request, 'profile.html', {'profile': user_profile})

@login_required
def edit_profile(request):
    user_profile, created = Profile.objects.get_or_create(user=request.user)

    # If they hit the "Save" button
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            form.save()
            return redirect('profile') # Send them back to their loadout card
            
    # If they are just loading the page to type
    else:
        form = ProfileForm(instance=user_profile)
        
    return render(request, 'edit_profile.html', {'form': form})

@login_required
def create_profile(request):
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = None
    
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            new_profile = form.save(commit=False)
            new_profile.user = request.user
            new_profile.save()
            return redirect('profile_success')
    else:
        form = ProfileForm(instance=profile)
    
    return render(request, 'mycalendar/signup.html', {'form': form})
